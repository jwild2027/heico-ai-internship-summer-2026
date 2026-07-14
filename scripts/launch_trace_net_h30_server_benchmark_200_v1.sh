#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-/data/trace_net/repos/trace-net-h30-canary}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="$VENV/bin/python"
RUNTIME="${TRACE_NET_BENCHMARK_RUNTIME:-/data/trace_net_runs/cognitive_benchmark_200_failure_repair_v1}"
BASE_URL="${TRACE_NET_BENCHMARK_BASE_URL:-http://127.0.0.1:8128}"
API_KEY="${TRACE_NET_BENCHMARK_API_KEY:-trace-net-gemma-cognitive-local}"
TIMEOUT="${TRACE_NET_BENCHMARK_TIMEOUT_SECONDS:-1200}"
GEMMA_URL="${TRACE_NET_BENCHMARK_GEMMA_URL:-http://127.0.0.1:11434/api/chat}"
GEMMA_TAGS_URL="${TRACE_NET_BENCHMARK_GEMMA_TAGS_URL:-http://127.0.0.1:11434/api/tags}"
GEMMA_MODEL="${TRACE_NET_BENCHMARK_GEMMA_MODEL:-gemma4:26b}"
GEMMA_TIMEOUT="${TRACE_NET_BENCHMARK_GEMMA_TIMEOUT_SECONDS:-1200}"
OUTPUT="$RUNTIME/trace_net_h30_server_benchmark_200_v1.json"
LOG="$RUNTIME/trace_net_h30_server_benchmark_200_v1_console.log"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
export TRACE_NET_REQUIRED_GEMMA_MODEL="$GEMMA_MODEL"
mkdir -p "$RUNTIME"

echo "============================================================"
echo "TRACE-NET H30 200-QUESTION SERVER BENCHMARK"
echo "============================================================"
echo "repo=$REPO"
echo "commit=$(git rev-parse HEAD)"
echo "base_url=$BASE_URL"
echo "output=$OUTPUT"
echo "console_log=$LOG"
echo "gemma_model=$GEMMA_MODEL"
echo "gemma_url=$GEMMA_URL"
echo "gemma_required_for_every_question=true"
echo

if pgrep -af "run_trace_net_h30_server_benchmark_200_v1.py" | grep -v "$$" >/dev/null 2>&1; then
    echo "A 200-question benchmark process already appears to be running:"
    pgrep -af "run_trace_net_h30_server_benchmark_200_v1.py" || true
    echo "Refusing to start a competing benchmark."
    exit 1
fi

echo "============================================================"
echo "VERIFYING H30 SERVICES"
echo "============================================================"

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:8118/health \
  | "$PYTHON" -c '
import json,sys
value=json.load(sys.stdin)
assert value.get("quality_status")=="PASS", value
assert value.get("route_count")==19, value
print("port_8118=PASS route_count=19")
'

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:8128/health \
  | "$PYTHON" -c '
import json,sys
value=json.load(sys.stdin)
assert value.get("quality_status")=="PASS", value
assert value.get("post_answer_validation") is True, value
print("port_8128=PASS post_answer_validation=true")
'

curl --fail-with-body --silent --show-error \
  http://172.17.0.1:8131/health \
  | "$PYTHON" -c '
import json,sys
value=json.load(sys.stdin)
assert value.get("quality_status")=="PASS", value
assert value.get("stream_normalization") is True, value
print("port_8131=PASS stream_normalization=true")
'

curl --fail-with-body --silent --show-error "$GEMMA_TAGS_URL" \
  | "$PYTHON" -c '
import json,os,sys
value=json.load(sys.stdin)
required=os.environ["TRACE_NET_REQUIRED_GEMMA_MODEL"]
names={str(row.get("name") or row.get("model")) for row in value.get("models",[]) if isinstance(row,dict)}
assert required in names, (required, sorted(names))
print(f"gemma_model={required} READY")
'

echo
echo "============================================================"
echo "COMPILING AND TESTING BENCHMARK HARNESS"
echo "============================================================"

"$PYTHON" -B -m py_compile \
  scripts/trace_net_h30_answer_boundary_v1.py \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/run_trace_net_h30_server_benchmark_200_v1.py \
  tests/unit/test_trace_net_h30_server_benchmark_200_v1.py \
  tests/unit/test_trace_net_h30_server_benchmark_gemma_response_fix_v1.py \
  tests/unit/test_trace_net_h30_benchmark_failure_repair_v1.py

"$PYTHON" -B -m pytest -q \
  tests/unit/test_trace_net_h30_server_benchmark_200_v1.py \
  tests/unit/test_trace_net_h30_server_benchmark_gemma_response_fix_v1.py \
  tests/unit/test_trace_net_h30_benchmark_failure_repair_v1.py \
  tests/unit/test_trace_net_cognitive_router_v1.py \
  tests/unit/test_trace_net_full_gemma_cognitive_v1.py

echo "benchmark_harness_tests=PASS"

echo
echo "============================================================"
echo "RUNNING 200 LIVE FULL-STACK QUESTIONS"
echo "============================================================"
echo "Progress will print TRACE_NET_START/DONE and GEMMA_START/DONE for every question."
echo "Every question uses $GEMMA_MODEL with think=false; three structured probes must pass before question 1."
echo "A checkpoint JSON is rewritten after every completed question."
echo

set +e
"$PYTHON" -B scripts/run_trace_net_h30_server_benchmark_200_v1.py \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --timeout-seconds "$TIMEOUT" \
  --gemma-url "$GEMMA_URL" \
  --gemma-tags-url "$GEMMA_TAGS_URL" \
  --gemma-model "$GEMMA_MODEL" \
  --gemma-timeout-seconds "$GEMMA_TIMEOUT" \
  --gemma-preflight-count 3 \
  --output "$OUTPUT" \
  --resume \
  2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}
set -e

echo
echo "============================================================"
echo "BENCHMARK RESULT"
echo "============================================================"

if [[ -f "$OUTPUT" ]]; then
    "$PYTHON" - "$OUTPUT" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
value=json.loads(path.read_text(encoding="utf-8"))
summary=value.get("summary") or {}
print(f"benchmark_status={value.get('benchmark_status')}")
print(f"quality_status={summary.get('quality_status')}")
print(f"completed={summary.get('question_count_completed')}/200")
print(f"pass_count={summary.get('pass_count')}")
print(f"semantic_answer_pass_count={summary.get('semantic_answer_pass_count')}")
print(f"failure_count={summary.get('failure_count')}")
print(f"routes_covered={len(summary.get('routes_covered') or [])}/19")
print(f"gemma_every_question={summary.get('gemma_every_question_count')}/200")
print(f"gemma_every_question_pass={summary.get('gemma_every_question_pass_count')}/200")
print(f"gemma_raw_pass={summary.get('gemma_raw_pass_count')}/200")
print(f"gemma_bounded_fallback={summary.get('gemma_bounded_fallback_count')}/200")
print(f"gemma_model={summary.get('gemma_model')}")
print(f"json={path}")
print(f"jsonl={value.get('output_paths',{}).get('jsonl')}")
print(f"checkpoint={value.get('output_paths',{}).get('checkpoint')}")
PY
else
    echo "Final JSON was not created. Inspect: $LOG"
fi

exit "$STATUS"
