#!/usr/bin/env bash
set -euo pipefail

COLOR="${1:-green}"
ACTION="${2:-start}"
REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
OLLAMA_URL="${TRACE_NET_NHA_OLLAMA_URL:-http://127.0.0.1:11434}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
RELEASE_DIR="${TRACE_NET_NHA_RELEASE_DIR:-$REPO/release_data/trace_net/nha_real_release_v1/phase4}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
POINTER_PATH="${TRACE_NET_BLUE_GREEN_POINTER_PATH:-/data/trace_net_runs/blue_green_frontdoor_v1/active_backend.json}"

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
  *)
    echo "usage: $0 [green|blue] [start|stop|status|ports]" >&2
    exit 2
    ;;
esac

RUNTIME_ROOT="${TRACE_NET_BLUE_GREEN_RUNTIME_ROOT:-/data/trace_net_runs/blue_green_v1}"
RUNTIME="$RUNTIME_ROOT/$COLOR"
ROUTER_KEY="trace-net-blue-green-${COLOR}-cognitive"
WRITER_KEY="trace-net-blue-green-${COLOR}-writer"
ROUTER_SESSION="trace-net-blue-green-${COLOR}-router-${ROUTER_PORT}"
WRITER_SESSION="trace-net-blue-green-${COLOR}-writer-${WRITER_PORT}"
NHA_SESSION="trace-net-blue-green-${COLOR}-nha-${NHA_PORT}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for command in tmux curl fuser; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 1; }
done

candidate_backend_url="http://127.0.0.1:$NHA_PORT"

print_ports() {
  printf '%s\n' \
    "color=$COLOR" \
    "router_port=$ROUTER_PORT" \
    "writer_port=$WRITER_PORT" \
    "nha_port=$NHA_PORT" \
    "benchmark_port=$BENCHMARK_PORT" \
    "candidate_backend_url=$candidate_backend_url"
}

active_backend_url() {
  if [[ ! -f "$POINTER_PATH" ]]; then
    return 0
  fi
  "$PYTHON" - "$POINTER_PATH" <<'PY'
import json, sys
from pathlib import Path
try:
    value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
print(str(value.get("backend_url") or "").rstrip("/"))
PY
}

stop_one() {
  local session="$1"
  local port="$2"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  fuser -k -TERM "${port}/tcp" 2>/dev/null || true
  sleep 0.5
  if fuser "${port}/tcp" >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

stop_candidate() {
  local active
  active="$(active_backend_url || true)"
  if [[ "$active" == "$candidate_backend_url" && "${TRACE_NET_BLUE_GREEN_ALLOW_STOP_ACTIVE:-0}" != "1" ]]; then
    echo "refusing_to_stop_active_backend=$candidate_backend_url" >&2
    echo "Set TRACE_NET_BLUE_GREEN_ALLOW_STOP_ACTIVE=1 only for intentional maintenance." >&2
    exit 3
  fi
  stop_one "$NHA_SESSION" "$NHA_PORT"
  stop_one "$WRITER_SESSION" "$WRITER_PORT"
  stop_one "$ROUTER_SESSION" "$ROUTER_PORT"
  echo "TRACE_NET_BLUE_GREEN_CANDIDATE_STOP=PASS"
  print_ports
}

wait_port() {
  local port="$1"
  "$PYTHON" - "$port" <<'PY'
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
raise SystemExit(f"port {port} failed to start")
PY
}

status_candidate() {
  local failed=0
  for port in "$ROUTER_PORT" "$WRITER_PORT" "$NHA_PORT"; do
    if ! curl --fail-with-body --silent --show-error --max-time 15 "http://127.0.0.1:$port/health"; then
      failed=1
    fi
    echo
  done
  print_ports
  if [[ "$failed" == "0" ]]; then
    echo "TRACE_NET_BLUE_GREEN_CANDIDATE_STATUS=PASS"
  else
    echo "TRACE_NET_BLUE_GREEN_CANDIDATE_STATUS=FAIL"
    return 1
  fi
}

if [[ "$ACTION" == "ports" ]]; then
  print_ports
  exit 0
fi
if [[ "$ACTION" == "stop" ]]; then
  stop_candidate
  exit 0
fi
if [[ "$ACTION" == "status" ]]; then
  status_candidate
  exit 0
fi
[[ "$ACTION" == "start" ]] || { echo "usage: $0 [green|blue] [start|stop|status|ports]" >&2; exit 2; }

for required in \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  scripts/trace_net_h30_phase19_route_completion_fastpath_v1.py \
  scripts/trace_net_h30_phase19_preservation_writer_v1.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 1; }
done
[[ -d "$RELEASE_DIR" ]] || { echo "missing_nha_release_dir=$RELEASE_DIR"; exit 1; }
[[ -d "$ENGRAM_DIR" ]] || { echo "missing_nha_engram_dir=$ENGRAM_DIR"; exit 1; }

curl --fail-with-body --silent --show-error --max-time 15 http://127.0.0.1:8117/health > "$RUNTIME/8117_health.json"
curl --fail-with-body --silent --show-error --max-time 15 http://127.0.0.1:8116/health > "$RUNTIME/8116_health.json"
curl --fail-with-body --silent --show-error --max-time 15 "$OLLAMA_URL/api/tags" | grep -Fq "$GEMMA_MODEL"

# Stale candidate processes are safe to stop before a new candidate launch.
# Production 8118/8128/8131 and the opposite color are never touched.
TRACE_NET_BLUE_GREEN_ALLOW_STOP_ACTIVE=0 stop_candidate >/dev/null 2>&1 || {
  if [[ "$(active_backend_url || true)" == "$candidate_backend_url" ]]; then
    echo "candidate_color_is_currently_active=$COLOR" >&2
    echo "Choose the opposite color for the next candidate." >&2
    exit 3
  fi
  stop_one "$NHA_SESSION" "$NHA_PORT"
  stop_one "$WRITER_SESSION" "$WRITER_PORT"
  stop_one "$ROUTER_SESSION" "$ROUTER_PORT"
}

cat > "/tmp/start_trace_net_blue_green_${COLOR}_router.sh" <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_H30_SHADOW_PLANNER_ENABLED=0
export TRACE_NET_H30_PLANNER_ROLLOUT_MODE=validate_only
export TRACE_NET_H30_PLANNER_EXECUTION_ENABLED=0
export TRACE_NET_H30_TYPED_EVIDENCE_ENABLED=1
export TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED=1
export TRACE_NET_H30_CLAIM_READY_EVIDENCE_MAX_RECORDS=32
export TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED=1
export TRACE_NET_H30_RETRIEVAL_DEADLINE_SECONDS=120
export TRACE_NET_H30_RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS=45
export TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS=16
export TRACE_NET_H30_RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL=10
export TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED=1
export TRACE_NET_H30_GRAPH_NODES_PATH="$REPO/local_data/organization/graph/graph_nodes.json"
export TRACE_NET_H30_GRAPH_EDGES_PATH="$REPO/local_data/organization/graph/graph_edges.json"
export TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED=1
export TRACE_NET_H30_PAGE_V2_ARTIFACT="$REPO/local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json"
export TRACE_NET_H30_PAGE_V3_ARTIFACT="$REPO/local_data/organization/trace_net/v3_page_intelligence/trace_net_v3_page_intelligence_cards_v1.json"
export TRACE_NET_H30_PAGE_TABLE_ARTIFACT="$REPO/local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_documents_v1.jsonl"
export TRACE_NET_H30_PAGE_OCR_ARTIFACT="$REPO/local_data/organization/trace_net/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1_records.jsonl"
export TRACE_NET_H30_PAGE_VISUAL_ARTIFACT="$REPO/local_data/organization/trace_net/confirmed_image_page_summary_v1_1/trace_net_confirmed_image_page_summary_v1_1.jsonl:$REPO/local_data/organization/trace_net/confirmed_image_llava_observations_v1_1_sample/trace_net_confirmed_image_llava_observations_v1_1.jsonl:$REPO/local_data/organization/trace_net/image_visual_evidence_pack_v1/trace_net_image_visual_evidence_pack_v1_records.jsonl:$REPO/local_data/organization/trace_net/corrected_visual_context_builder_v35_4/trace_net_corrected_visual_context_cards_v35_4.jsonl"
export TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED=1
export TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS:-2}"
export TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS:-2}"
export TRACE_NET_H30_PHASE19_ATA_MAX_CALLS="${TRACE_NET_H30_PHASE19_ATA_MAX_CALLS:-2}"
exec "$PYTHON" -u -B scripts/serve_trace_net_cognitive_router_v1.py \\
  --host 127.0.0.1 \\
  --port "$ROUTER_PORT" \\
  --unified-base-url http://127.0.0.1:8117 \\
  --guided-base-url http://127.0.0.1:8116 \\
  --unified-api-key "${TRACE_NET_UNIFIED_KEY:-trace-net-canary-local}" \\
  --api-key "$ROUTER_KEY" \\
  --timeout-seconds 1200 \\
  --max-concurrency 2 \\
  --queue-timeout-seconds 1200
INNER

cat > "/tmp/start_trace_net_blue_green_${COLOR}_writer.sh" <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_GEMMA_KEEP_ALIVE="${TRACE_NET_GEMMA_KEEP_ALIVE:-1h}"
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED=1
export TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH="$REPO/local_data/organization/trace_net/engram_skill_cards_v1/trace_net_engram_skill_cards_v1.json"
export TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED=1
export TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED=1
export TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED=1
export TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED=1
export TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES=exact_identifier_lookup,exact_table_ipl_lookup,ata_system_discovery
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS=16
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS=12000
export TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS=1
export TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS=45
export TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS=210
export TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS=20
export TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS=8
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS=512
export TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=1
export TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS="${TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS:-384}"
exec "$PYTHON" -u -B scripts/serve_trace_net_full_gemma_cognitive_v1.py \\
  --host 127.0.0.1 \\
  --port "$WRITER_PORT" \\
  --cognitive-base-url "http://127.0.0.1:$ROUTER_PORT" \\
  --cognitive-api-key "$ROUTER_KEY" \\
  --gemma-base-url "$OLLAMA_URL/v1" \\
  --gemma-api-key ollama \\
  --gemma-model "$GEMMA_MODEL" \\
  --api-key "$WRITER_KEY" \\
  --timeout-seconds 210 \\
  --max-concurrency 1 \\
  --queue-timeout-seconds 30
INNER

cat > "/tmp/start_trace_net_blue_green_${COLOR}_nha.sh" <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/serve_trace_net_nha_phase16_gemma_proxy_v1.py \\
  --host 127.0.0.1 \\
  --port "$NHA_PORT" \\
  --mode gated \\
  --phase4-dir "$RELEASE_DIR" \\
  --nha-engram-dir "$ENGRAM_DIR" \\
  --upstream-url "http://127.0.0.1:$WRITER_PORT" \\
  --upstream-api-key "$WRITER_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --upstream-model "$PUBLIC_MODEL" \\
  --ollama-url "$OLLAMA_URL" \\
  --gemma-model "$GEMMA_MODEL" \\
  --telemetry-path "$RUNTIME/nha_telemetry.jsonl" \\
  --timeout-seconds 300 \\
  --gemma-timeout-seconds 180 \\
  --gemma-max-tokens 512
INNER

chmod +x \
  "/tmp/start_trace_net_blue_green_${COLOR}_router.sh" \
  "/tmp/start_trace_net_blue_green_${COLOR}_writer.sh" \
  "/tmp/start_trace_net_blue_green_${COLOR}_nha.sh"

tmux new-session -d -s "$ROUTER_SESSION" \
  "bash /tmp/start_trace_net_blue_green_${COLOR}_router.sh 2>&1 | tee '$RUNTIME/router.log'"
wait_port "$ROUTER_PORT"

tmux new-session -d -s "$WRITER_SESSION" \
  "bash /tmp/start_trace_net_blue_green_${COLOR}_writer.sh 2>&1 | tee '$RUNTIME/writer.log'"
wait_port "$WRITER_PORT"

tmux new-session -d -s "$NHA_SESSION" \
  "bash /tmp/start_trace_net_blue_green_${COLOR}_nha.sh 2>&1 | tee '$RUNTIME/nha.log'"
wait_port "$NHA_PORT"

curl --fail-with-body --silent --show-error "http://127.0.0.1:$ROUTER_PORT/health" > "$RUNTIME/router_health.json"
curl --fail-with-body --silent --show-error "http://127.0.0.1:$WRITER_PORT/health" > "$RUNTIME/writer_health.json"
curl --fail-with-body --silent --show-error "http://127.0.0.1:$NHA_PORT/health" > "$RUNTIME/nha_health.json"

"$PYTHON" - "$RUNTIME/router_health.json" "$RUNTIME/writer_health.json" "$RUNTIME/nha_health.json" <<'PY'
import json, sys
from pathlib import Path
router=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
writer=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
nha=json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
fail=[]
if router.get("quality_status") != "PASS": fail.append("router_quality")
if (router.get("phase19_route_completion_fastpath") or {}).get("enabled") is not True: fail.append("route_completion_disabled")
if writer.get("quality_status") != "PASS": fail.append("writer_quality")
if (writer.get("phase19_preservation_writer") or {}).get("enabled") is not True: fail.append("preservation_writer_disabled")
if nha.get("quality_status") != "PASS": fail.append("nha_quality")
for key in ("upstream_ready", "gemma_ready", "engram_ready"):
    if nha.get(key) is not True: fail.append("nha_" + key)
if fail:
    raise SystemExit("candidate health failed: " + ",".join(fail))
print("TRACE_NET_BLUE_GREEN_CANDIDATE_HEALTH=PASS")
PY

cat > "$RUNTIME/candidate.json" <<JSON
{
  "schema_version": "trace_net_blue_green_candidate_v1",
  "quality_status": "PASS",
  "color": "$COLOR",
  "router_url": "http://127.0.0.1:$ROUTER_PORT",
  "writer_url": "http://127.0.0.1:$WRITER_PORT",
  "nha_url": "$candidate_backend_url",
  "benchmark_port": $BENCHMARK_PORT,
  "production_ports_touched": [],
  "rollback_handler_present": false
}
JSON

echo "TRACE_NET_BLUE_GREEN_CANDIDATE_START=PASS"
print_ports
