#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-/data/trace_net/repos/trace-net-canary}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="$VENV/bin/python"
RUNTIME="${TRACE_NET_RUNTIME_DIR:-/data/trace_net_runs/cognitive_openwebui_v1}"
UNIFIED_URL="${TRACE_NET_UNIFIED_URL:-http://127.0.0.1:8117}"
GUIDED_URL="${TRACE_NET_GUIDED_URL:-http://127.0.0.1:8116}"
UNIFIED_KEY="${TRACE_NET_UNIFIED_KEY:-trace-net-canary-local}"
COGNITIVE_KEY="${TRACE_NET_COGNITIVE_KEY:-trace-net-cognitive-local}"
GEMMA_KEY="${TRACE_NET_GEMMA_COGNITIVE_KEY:-trace-net-gemma-cognitive-local}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
GEMMA_KEEP_ALIVE="${TRACE_NET_GEMMA_KEEP_ALIVE:-1h}"
# Off by default: the shadow planner is an advisory/observational LLM planner
# that does not influence routing or retrieval (routes and tunnels stay
# deterministic), but when enabled it issues a second Gemma call per question in
# addition to the answer writer. The mature architecture targets zero or one
# Gemma call per question, never two, so this is disabled by default. Set
# TRACE_NET_H30_SHADOW_PLANNER_ENABLED=1 to re-enable it for planner evaluation.
SHADOW_PLANNER_ENABLED="${TRACE_NET_H30_SHADOW_PLANNER_ENABLED:-0}"
SHADOW_PLANNER_BASE_URL="${TRACE_NET_H30_SHADOW_PLANNER_BASE_URL:-http://127.0.0.1:11434/v1}"
SHADOW_PLANNER_API_KEY="${TRACE_NET_H30_SHADOW_PLANNER_API_KEY:-ollama}"
SHADOW_PLANNER_MODEL="${TRACE_NET_H30_SHADOW_PLANNER_MODEL:-$GEMMA_MODEL}"
SHADOW_PLANNER_TIMEOUT="${TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS:-300}"
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: capture validated-planner rollout settings.
PLANNER_ROLLOUT_MODE="${TRACE_NET_H30_PLANNER_ROLLOUT_MODE:-validate_only}"
PLANNER_EXECUTION_ENABLED="${TRACE_NET_H30_PLANNER_EXECUTION_ENABLED:-0}"
PLANNER_MAX_LATENCY_MS="${TRACE_NET_H30_PLANNER_MAX_LATENCY_MS:-90000}"
PLANNER_BREAKER_FAILURE_THRESHOLD="${TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD:-2}"
PLANNER_BREAKER_SECONDS="${TRACE_NET_H30_PLANNER_BREAKER_SECONDS:-300}"
PLANNER_CANONICAL_BRIDGE_ENABLED="${TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED:-1}"
PLANNER_REQUIRE_ROUTE="${TRACE_NET_H30_PLANNER_REQUIRE_ROUTE:-1}"
ENGRAM_SKILL_SHADOW_ENABLED="${TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED:-1}"
ENGRAM_SKILL_CARDS_PATH="${TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH:-$REPO/local_data/organization/trace_net/engram_skill_cards_v1/trace_net_engram_skill_cards_v1.json}"
ENGRAM_SKILL_SHADOW_MAX_SKILLS="${TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS:-3}"
ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED="${TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED:-0}"
ENGRAM_SKILL_PLANNER_GUIDANCE_MAX_CHARS="${TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_MAX_CHARS:-3200}"
# Mature-stack evidence pipeline: typed evidence envelope, evidence-aware answer
# modes (one Gemma call only for confirmed-direct, deterministic rendering
# otherwise), and the final Self-RAG deterministic validator are enabled by
# default. Set the matching TRACE_NET_H30_* env var to 0 to roll any of them back.
TYPED_EVIDENCE_ENABLED="${TRACE_NET_H30_TYPED_EVIDENCE_ENABLED:-1}"
CLAIM_READY_EVIDENCE_ENABLED="${TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED:-1}"
CLAIM_READY_EVIDENCE_MAX_RECORDS="${TRACE_NET_H30_CLAIM_READY_EVIDENCE_MAX_RECORDS:-32}"
EVIDENCE_AWARE_ANSWER_MODES_ENABLED="${TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED:-1}"
EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS="${TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS:-6}"
FINAL_ENGRAM_ROLLOUT_ENABLED="${TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED:-1}"
FINAL_ENGRAM_MAX_FOLLOWUPS="${TRACE_NET_H30_FINAL_ENGRAM_MAX_FOLLOWUPS:-3}"
FINAL_ENGRAM_MAX_REPAIRS="${TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS:-1}"
# Evidence synthesis (writer): let Gemma write evidence-bearing answers for
# candidate/visual/semantic/conflict modes instead of a deterministic template.
# Strict claim guardrails (unsupported identifier, dangerous claim without
# authority, positive-proof patterns) still bound the output and fall back to
# the safe deterministic render on any violation. Set =0 to roll back.
EVIDENCE_SYNTHESIS_ENABLED="${TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED:-1}"
# TRACE_NET_H30_PHASE4_CONSTRAINED_WRITER_ENV_V1
# The legacy free-form writer is suppressed while this is enabled. The final
# Phase 3 answer is sent through at most one strict JSON wording call on the
# canary routes below, with deterministic fallback on any failure.
CONSTRAINED_WRITER_ENABLED="${TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED:-1}"
CONSTRAINED_WRITER_ROUTES="${TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES:-exact_identifier_lookup,exact_table_ipl_lookup,ata_system_discovery}"
CONSTRAINED_WRITER_MAX_CITATIONS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS:-16}"
CONSTRAINED_WRITER_MAX_OUTPUT_CHARS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS:-12000}"
CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS="${TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS:-1}"
# TRACE_NET_H30_PHASE4_LATENCY_GUARD_V1
# The public benchmark uses a 240-second client timeout. Keep the writer below
# that boundary and reserve time to validate and return the Phase 3 fallback.
CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS:-45}"
CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS:-210}"
CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS:-20}"
CONSTRAINED_WRITER_MIN_CALL_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS:-8}"
CONSTRAINED_WRITER_MAX_TOKENS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS:-512}"
# TRACE_NET_H30_PHASE19_UPSTREAM_LATENCY_WRITER_ENV_V1
PHASE19_ROUTE_COMPLETION_ENABLED="${TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED:-0}"
PHASE19_EXACT_IDENTIFIER_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS:-2}"
PHASE19_EXACT_TABLE_MAX_CALLS="${TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS:-2}"
PHASE19_ATA_MAX_CALLS="${TRACE_NET_H30_PHASE19_ATA_MAX_CALLS:-2}"
PHASE19_PRESERVATION_WRITER_ENABLED="${TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED:-0}"
PHASE19_PRESERVATION_MAX_TOKENS="${TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS:-384}"
GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS="${TRACE_NET_H30_GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS:-30}"
PUBLIC_BRIDGE_TIMEOUT_SECONDS="${TRACE_NET_H30_PUBLIC_BRIDGE_TIMEOUT_SECONDS:-225}"
# General retrieval budget (router, all routes): overall wall-clock deadline,
# per-tunnel upstream timeout, max executed tunnels, and per-tunnel candidate
# cap. This bounds the serial upstream fan-out that otherwise let a single
# question run for hundreds of seconds. Set ..._RETRIEVAL_BUDGET_ENABLED=0 to
# roll back to the unbounded 1200s-per-call behavior.
RETRIEVAL_BUDGET_ENABLED="${TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED:-1}"
RETRIEVAL_DEADLINE_SECONDS="${TRACE_NET_H30_RETRIEVAL_DEADLINE_SECONDS:-120}"
RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS="${TRACE_NET_H30_RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS:-45}"
RETRIEVAL_MAX_TUNNELS="${TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS:-16}"
RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL="${TRACE_NET_H30_RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL:-10}"
# Deterministic graph-source traversal (router): connect a query's exact/partial
# part, ATA chapter, or nomenclature noun to the pages and source traces that
# mention it, added to the envelope as guidance-only candidate/navigation leads
# (never proof). Set =0 to roll back.
GRAPH_RETRIEVAL_ENABLED="${TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED:-1}"
GRAPH_NODES_PATH="${TRACE_NET_H30_GRAPH_NODES_PATH:-$REPO/local_data/organization/graph/graph_nodes.json}"
GRAPH_EDGES_PATH="${TRACE_NET_H30_GRAPH_EDGES_PATH:-$REPO/local_data/organization/graph/graph_edges.json}"
# Exact-page content bridge (router): a supplied canonical page id assembles a
# typed page-content pack (V2/V3/OCR/table/visual) from the exact graph page.
# Guidance only; read-only; adds no second Gemma call. Set =0 to roll back.
PAGE_CONTENT_BRIDGE_ENABLED="${TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED:-1}"
PAGE_V2_ARTIFACT="${TRACE_NET_H30_PAGE_V2_ARTIFACT:-$REPO/local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json}"
PAGE_V3_ARTIFACT="${TRACE_NET_H30_PAGE_V3_ARTIFACT:-$REPO/local_data/organization/trace_net/v3_page_intelligence/trace_net_v3_page_intelligence_cards_v1.json}"
PAGE_TABLE_ARTIFACT="${TRACE_NET_H30_PAGE_TABLE_ARTIFACT:-$REPO/local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_documents_v1.jsonl}"
# Per-page OCR text (tesseract full scan) and visual guidance. Visual guidance is
# merged across several real artifacts (path-separator list). Point these at the
# data repo when the canary repo does not itself hold local_data.
PAGE_OCR_ARTIFACT="${TRACE_NET_H30_PAGE_OCR_ARTIFACT:-$REPO/local_data/organization/trace_net/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1_records.jsonl}"
PAGE_VISUAL_ARTIFACT="${TRACE_NET_H30_PAGE_VISUAL_ARTIFACT:-$REPO/local_data/organization/trace_net/confirmed_image_page_summary_v1_1/trace_net_confirmed_image_page_summary_v1_1.jsonl:$REPO/local_data/organization/trace_net/confirmed_image_llava_observations_v1_1_sample/trace_net_confirmed_image_llava_observations_v1_1.jsonl:$REPO/local_data/organization/trace_net/image_visual_evidence_pack_v1/trace_net_image_visual_evidence_pack_v1_records.jsonl:$REPO/local_data/organization/trace_net/corrected_visual_context_builder_v35_4/trace_net_corrected_visual_context_cards_v35_4.jsonl}"
RUN_CRITICAL_LIVE_ROUTE_SMOKE="${TRACE_NET_RUN_CRITICAL_LIVE_ROUTE_SMOKE:-0}"

case "$PLANNER_ROLLOUT_MODE" in
  validate_only|narrow|broad|mature) ;;
  *)
    echo "invalid_planner_rollout_mode=$PLANNER_ROLLOUT_MODE"
    exit 1
    ;;
esac

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for required in \
  scripts/operations/router/serve_trace_net_cognitive_router_v1.py \
  src/trace_net/router/trace_net_h30_shadow_planner_v1.py \
  src/trace_net/engram/trace_net_h30_engram_skill_planner_guidance_v1.py \
  src/trace_net/context/trace_net_h30_typed_evidence_envelope_v1.py \
  src/trace_net/context/trace_net_h30_claim_ready_evidence_v1.py \
  scripts/maintenance/context/check_trace_net_h30_claim_ready_evidence_v1.py \
  src/trace_net/writing/trace_net_h30_content_reconstruction_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_content_reconstruction_v1.py \
  src/trace_net/writing/trace_net_h30_constrained_gemma_writer_v1.py \
  src/trace_net/router/trace_net_h30_phase19_route_completion_fastpath_v1.py \
  src/trace_net/writing/trace_net_h30_phase19_preservation_writer_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_constrained_gemma_writer_v1.py \
  src/trace_net/writing/trace_net_h30_evidence_aware_answer_modes_v1.py \
  src/trace_net/writing/trace_net_h30_exact_page_answer_mode_v1.py \
  src/trace_net/validation/trace_net_h30_answer_quality_v1.py \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1.py \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1_1.py \
  scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/operations/serving/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  src/trace_net/serving/trace_net_h30_cold_start_streaming_v1.py \
  scripts/benchmark/run_trace_net_cognitive_route_smoke_v1.py; do
  if [[ ! -f "$required" ]]; then
    echo "missing_required_file=$required"
    exit 1
  fi
done

# TRACE_NET_H30_PHASE0_6_0_7_PUBLIC_ANSWER_GATE_REQUIRED_V1
for public_answer_required in \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1_2.py \
  scripts/benchmark/core/check_trace_net_h30_public_answer_golden_v1.py \
  tests/fixtures/trace_net_h30_tiff_grounded20_public_answer_golden_v1.json; do
  if [[ ! -f "$public_answer_required" ]]; then
    echo "missing_public_answer_gate_file=$public_answer_required"
    exit 1
  fi
done

# TRACE_NET_H30_PHASE1_PUBLIC_ANSWER_CONTRACT_REQUIRED_V1
for phase1_public_required in \
  src/trace_net/writing/trace_net_h30_public_answer_contract_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_public_answer_contract_v1.py; do
  if [[ ! -f "$phase1_public_required" ]]; then
    echo "missing_phase1_public_answer_contract_file=$phase1_public_required"
    exit 1
  fi
done

# TRACE_NET_H30_FINAL_PHASES6_10_REQUIRED_FILES_V1
for final_required in \
  src/trace_net/validation/trace_net_h30_final_engram_rollout_v1.py \
  scripts/maintenance/engram/check_trace_net_h30_final_engram_rollout_v1.py \
  scripts/benchmark/run_trace_net_h30_final_rollout_live_smoke_v1.py \
  scripts/benchmark/run_trace_net_h30_final_engram_benchmark_v1.py; do
  if [[ ! -f "$final_required" ]]; then
    echo "missing_final_rollout_file=$final_required"
    exit 1
  fi
done

for command in tmux curl fuser ip; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 1; }
done

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
if [[ -z "$BRIDGE_HOST" ]]; then
  BRIDGE_HOST="172.17.0.1"
fi

echo "============================================================"
echo "VERIFYING EXISTING TRACE-NET UPSTREAMS"
echo "============================================================"

curl --fail-with-body --silent --show-error "$UNIFIED_URL/health" > "$RUNTIME/8117_health.json"
curl --fail-with-body --silent --show-error "$GUIDED_URL/health" > "$RUNTIME/8116_health.json"

"$PYTHON" - <<PY
import json
from pathlib import Path
for name in ("8117_health.json", "8116_health.json"):
    data=json.loads((Path("$RUNTIME")/name).read_text())
    print(name, data.get("quality_status"), data.get("module") or data.get("service"))
    if data.get("quality_status") not in {"PASS", "WARN"}:
        raise SystemExit(f"upstream health failed: {name}")
PY

if ! curl -sS --max-time 15 http://127.0.0.1:11434/api/tags | grep -Fq "$GEMMA_MODEL"; then
  echo "missing_ollama_model=$GEMMA_MODEL"
  exit 1
fi


echo
echo "============================================================"
echo "PRELOADING GEMMA IN OLLAMA"
echo "============================================================"

"$PYTHON" - "$GEMMA_MODEL" "$GEMMA_KEEP_ALIVE" "$RUNTIME/gemma_preload.json" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

model, keep_alive, output = sys.argv[1:]
payload = {"model": model, "prompt": "", "stream": False, "keep_alive": keep_alive}
request = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.monotonic()
with urllib.request.urlopen(request, timeout=1200) as response:
    result = json.loads(response.read().decode("utf-8", errors="replace"))
elapsed_ms = round((time.monotonic() - started) * 1000.0, 3)
result["preload_wall_ms"] = elapsed_ms
result["requested_keep_alive"] = keep_alive
Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
if result.get("error"):
    raise SystemExit("Ollama preload returned an error: " + str(result["error"]))
print("gemma_preload_status=PASS")
print(f"gemma_preload_wall_ms={elapsed_ms}")
print(f"gemma_keep_alive={keep_alive}")
PY

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:11434/api/ps \
  > "$RUNTIME/ollama_ps_after_preload.json"

"$PYTHON" - "$GEMMA_MODEL" "$RUNTIME/ollama_ps_after_preload.json" <<'PY'
import json
import sys
from pathlib import Path
model, filename = sys.argv[1:]
data = json.loads(Path(filename).read_text(encoding="utf-8"))
names = {
    str(row.get("name") or row.get("model"))
    for row in data.get("models", [])
    if isinstance(row, dict)
}
print("ollama_loaded_models=" + ",".join(sorted(names)))
if model not in names:
    raise SystemExit(f"preloaded model is not resident according to /api/ps: {model}")
print("gemma_resident_status=PASS")
PY

command -v ollama >/dev/null && ollama ps || true

echo
echo "============================================================"
echo "COMPILING H30 COGNITIVE STACK"
echo "============================================================"

"$PYTHON" -m py_compile \
  scripts/operations/router/serve_trace_net_cognitive_router_v1.py \
  src/trace_net/router/trace_net_h30_shadow_planner_v1.py \
  src/trace_net/engram/trace_net_h30_engram_skill_planner_guidance_v1.py \
  scripts/maintenance/engram/check_trace_net_engram_skill_planner_guidance_v1.py \
  scripts/benchmark/run_trace_net_engram_skill_planner_guidance_live_smoke_v1.py \
  src/trace_net/context/trace_net_h30_typed_evidence_envelope_v1.py \
  scripts/maintenance/context/check_trace_net_h30_typed_evidence_envelope_v1.py \
  src/trace_net/context/trace_net_h30_claim_ready_evidence_v1.py \
  scripts/maintenance/context/check_trace_net_h30_claim_ready_evidence_v1.py \
  src/trace_net/writing/trace_net_h30_content_reconstruction_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_content_reconstruction_v1.py \
  src/trace_net/writing/trace_net_h30_constrained_gemma_writer_v1.py \
  src/trace_net/router/trace_net_h30_phase19_route_completion_fastpath_v1.py \
  src/trace_net/writing/trace_net_h30_phase19_preservation_writer_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_constrained_gemma_writer_v1.py \
  scripts/benchmark/run_trace_net_h30_typed_evidence_live_smoke_v1.py \
  src/trace_net/writing/trace_net_h30_evidence_aware_answer_modes_v1.py \
  src/trace_net/writing/trace_net_h30_exact_page_answer_mode_v1.py \
  src/trace_net/validation/trace_net_h30_answer_quality_v1.py \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1.py \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1_1.py \
  src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1_2.py \
  src/trace_net/writing/trace_net_h30_public_answer_contract_v1.py \
  scripts/maintenance/writing/check_trace_net_h30_public_answer_contract_v1.py \
  scripts/maintenance/visual/check_trace_net_h30_evidence_aware_answer_modes_v1.py \
  scripts/benchmark/run_trace_net_h30_evidence_aware_answer_modes_live_smoke_v1.py \
  scripts/maintenance/operations/check_trace_net_h30_shadow_planner_v1.py \
  scripts/benchmark/run_trace_net_h30_shadow_planner_benchmark_v1.py \
  scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/operations/serving/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  src/trace_net/serving/trace_net_h30_cold_start_streaming_v1.py \
  scripts/benchmark/run_trace_net_cognitive_route_smoke_v1.py

echo "compile_status=PASS"

# TRACE_NET_NHA_PHASE20_LEGACY_TEST_ENV_ISOLATION_V1
TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=0 "$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_cognitive_router_v1.py \
  tests/unit/test_trace_net_h30_shadow_planner_v1.py \
  tests/unit/test_trace_net_engram_skill_planner_guidance_v1.py \
  tests/unit/test_trace_net_h30_typed_evidence_envelope_v1.py \
  tests/unit/test_trace_net_h30_claim_ready_evidence_v1.py \
  tests/unit/test_trace_net_h30_content_reconstruction_v1.py \
  tests/unit/test_check_trace_net_h30_content_reconstruction_v1.py \
  tests/unit/test_trace_net_h30_constrained_gemma_writer_v1.py \
  tests/unit/test_trace_net_h30_phase19_route_completion_fastpath_v1.py \
  tests/unit/test_trace_net_h30_phase19_preservation_writer_v1.py \
  tests/unit/test_check_trace_net_h30_constrained_gemma_writer_v1.py \
  tests/unit/test_trace_net_h30_phase4_runtime_wiring_v1.py \
  tests/unit/test_trace_net_h30_phase4_latency_guard_v1.py \
  tests/unit/test_trace_net_h30_evidence_aware_answer_modes_v1.py \
  tests/unit/test_trace_net_h30_exact_page_answer_integration_v1.py \
  tests/unit/test_trace_net_h30_answer_quality_v1.py \
  tests/unit/test_trace_net_h30_chatgpt_answer_presentation_v1.py \
  tests/unit/test_trace_net_h30_chatgpt_answer_presentation_v1_1.py \
  tests/unit/test_trace_net_h30_chatgpt_answer_presentation_v1_2.py \
  tests/unit/test_trace_net_h30_public_answer_golden_v1.py \
  tests/unit/test_trace_net_h30_public_answer_contract_v1.py \
  tests/unit/test_check_trace_net_h30_public_answer_contract_v1.py \
  tests/unit/test_trace_net_full_gemma_cognitive_v1.py \
  tests/unit/test_trace_net_h30_cold_start_streaming_v1.py

echo "unit_test_status=PASS"

# TRACE_NET_H30_FINAL_PHASES6_10_COMPILE_TEST_V1
"$PYTHON" -m py_compile \
  src/trace_net/validation/trace_net_h30_final_engram_rollout_v1.py \
  scripts/maintenance/engram/check_trace_net_h30_final_engram_rollout_v1.py \
  scripts/benchmark/run_trace_net_h30_final_rollout_live_smoke_v1.py \
  scripts/benchmark/run_trace_net_h30_final_engram_benchmark_v1.py

echo "final_rollout_compile_status=PASS"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_h30_final_engram_rollout_v1.py

echo "final_rollout_unit_test_status=PASS"


stop_session() {
  local session="$1"
  local port="$2"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  fuser -k -TERM "${port}/tcp" 2>/dev/null || true
  sleep 1
  if fuser "${port}/tcp" >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

stop_session trace-net-cognitive-8118 8118
stop_session trace-net-gemma-cognitive-8128 8128
stop_session trace-net-openwebui-cognitive-8131 8131

cat > /tmp/start_trace_net_cognitive_8118.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_H30_SHADOW_PLANNER_ENABLED="$SHADOW_PLANNER_ENABLED"
export TRACE_NET_H30_SHADOW_PLANNER_BASE_URL="$SHADOW_PLANNER_BASE_URL"
export TRACE_NET_H30_SHADOW_PLANNER_API_KEY="$SHADOW_PLANNER_API_KEY"
export TRACE_NET_H30_SHADOW_PLANNER_MODEL="$SHADOW_PLANNER_MODEL"
export TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS="$SHADOW_PLANNER_TIMEOUT"
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: propagate settings into the tmux process.
export TRACE_NET_H30_PLANNER_ROLLOUT_MODE="$PLANNER_ROLLOUT_MODE"
export TRACE_NET_H30_PLANNER_EXECUTION_ENABLED="$PLANNER_EXECUTION_ENABLED"
export TRACE_NET_H30_PLANNER_MAX_LATENCY_MS="$PLANNER_MAX_LATENCY_MS"
export TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD="$PLANNER_BREAKER_FAILURE_THRESHOLD"
export TRACE_NET_H30_PLANNER_BREAKER_SECONDS="$PLANNER_BREAKER_SECONDS"
export TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED="$PLANNER_CANONICAL_BRIDGE_ENABLED"
export TRACE_NET_H30_PLANNER_REQUIRE_ROUTE="$PLANNER_REQUIRE_ROUTE"
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED="$ENGRAM_SKILL_SHADOW_ENABLED"
export TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH="$ENGRAM_SKILL_CARDS_PATH"
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS="$ENGRAM_SKILL_SHADOW_MAX_SKILLS"
export TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED="$ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED"
export TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_MAX_CHARS="$ENGRAM_SKILL_PLANNER_GUIDANCE_MAX_CHARS"
export TRACE_NET_H30_TYPED_EVIDENCE_ENABLED="$TYPED_EVIDENCE_ENABLED"
export TRACE_NET_H30_CLAIM_READY_EVIDENCE_ENABLED="$CLAIM_READY_EVIDENCE_ENABLED"
export TRACE_NET_H30_CLAIM_READY_EVIDENCE_MAX_RECORDS="$CLAIM_READY_EVIDENCE_MAX_RECORDS"
export TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED="$RETRIEVAL_BUDGET_ENABLED"
export TRACE_NET_H30_RETRIEVAL_DEADLINE_SECONDS="$RETRIEVAL_DEADLINE_SECONDS"
export TRACE_NET_H30_RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS="$RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS"
export TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS="$RETRIEVAL_MAX_TUNNELS"
export TRACE_NET_H30_RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL="$RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL"
export TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED="$PHASE19_ROUTE_COMPLETION_ENABLED"
export TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS="$PHASE19_EXACT_IDENTIFIER_MAX_CALLS"
export TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS="$PHASE19_EXACT_TABLE_MAX_CALLS"
export TRACE_NET_H30_PHASE19_ATA_MAX_CALLS="$PHASE19_ATA_MAX_CALLS"
export TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED="$GRAPH_RETRIEVAL_ENABLED"
export TRACE_NET_H30_GRAPH_NODES_PATH="$GRAPH_NODES_PATH"
export TRACE_NET_H30_GRAPH_EDGES_PATH="$GRAPH_EDGES_PATH"
export TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED="$PAGE_CONTENT_BRIDGE_ENABLED"
export TRACE_NET_H30_PAGE_V2_ARTIFACT="$PAGE_V2_ARTIFACT"
export TRACE_NET_H30_PAGE_V3_ARTIFACT="$PAGE_V3_ARTIFACT"
export TRACE_NET_H30_PAGE_TABLE_ARTIFACT="$PAGE_TABLE_ARTIFACT"
export TRACE_NET_H30_PAGE_OCR_ARTIFACT="$PAGE_OCR_ARTIFACT"
export TRACE_NET_H30_PAGE_VISUAL_ARTIFACT="$PAGE_VISUAL_ARTIFACT"
exec "$PYTHON" -u -B scripts/operations/router/serve_trace_net_cognitive_router_v1.py \\
  --host 127.0.0.1 \\
  --port 8118 \\
  --unified-base-url "$UNIFIED_URL" \\
  --guided-base-url "$GUIDED_URL" \\
  --unified-api-key "$UNIFIED_KEY" \\
  --api-key "$COGNITIVE_KEY" \\
  --timeout-seconds 1200 \\
  --max-concurrency 2 \\
  --queue-timeout-seconds 1200
INNER

cat > /tmp/start_trace_net_gemma_cognitive_8128.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_GEMMA_KEEP_ALIVE="$GEMMA_KEEP_ALIVE"
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED="$ENGRAM_SKILL_SHADOW_ENABLED"
export TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH="$ENGRAM_SKILL_CARDS_PATH"
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS="$ENGRAM_SKILL_SHADOW_MAX_SKILLS"
export TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED="$EVIDENCE_AWARE_ANSWER_MODES_ENABLED"
export TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS="$EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS"
export TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED="$FINAL_ENGRAM_ROLLOUT_ENABLED"
export TRACE_NET_H30_FINAL_ENGRAM_MAX_FOLLOWUPS="$FINAL_ENGRAM_MAX_FOLLOWUPS"
export TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS="$FINAL_ENGRAM_MAX_REPAIRS"
export TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED="$EVIDENCE_SYNTHESIS_ENABLED"
# TRACE_NET_H30_PHASE4_CONSTRAINED_WRITER_EXPORT_V1
export TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED="$CONSTRAINED_WRITER_ENABLED"
export TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES="$CONSTRAINED_WRITER_ROUTES"
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS="$CONSTRAINED_WRITER_MAX_CITATIONS"
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS="$CONSTRAINED_WRITER_MAX_OUTPUT_CHARS"
export TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS="$CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS"
export TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS="$CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS"
export TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS="$CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS"
export TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS="$CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS"
export TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS="$CONSTRAINED_WRITER_MIN_CALL_SECONDS"
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS="$CONSTRAINED_WRITER_MAX_TOKENS"
export TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED="$PHASE19_PRESERVATION_WRITER_ENABLED"
export TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS="$PHASE19_PRESERVATION_MAX_TOKENS"
exec "$PYTHON" -u -B scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py \\
  --host 127.0.0.1 \\
  --port 8128 \\
  --cognitive-base-url http://127.0.0.1:8118 \\
  --cognitive-api-key "$COGNITIVE_KEY" \\
  --gemma-base-url http://127.0.0.1:11434/v1 \\
  --gemma-api-key ollama \\
  --gemma-model "$GEMMA_MODEL" \\
  --api-key "$GEMMA_KEY" \\
  --timeout-seconds "$CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS" \\
  --max-concurrency 1 \\
  --queue-timeout-seconds "$GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS"
INNER

cat > /tmp/start_trace_net_openwebui_cognitive_8131.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/operations/serving/serve_trace_net_openwebui_cognitive_bridge_v1.py \\
  --host "$BRIDGE_HOST" \\
  --port 8131 \\
  --upstream-url http://127.0.0.1:8128 \\
  --upstream-api-key "$GEMMA_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --timeout-seconds "$PUBLIC_BRIDGE_TIMEOUT_SECONDS"
INNER

chmod +x \
  /tmp/start_trace_net_cognitive_8118.sh \
  /tmp/start_trace_net_gemma_cognitive_8128.sh \
  /tmp/start_trace_net_openwebui_cognitive_8131.sh

wait_port() {
  local host="$1"
  local port="$2"
  "$PYTHON" - "$host" "$port" <<'PY'
import socket, sys, time
host=sys.argv[1]
port=int(sys.argv[2])
deadline=time.time()+180
while time.time()<deadline:
    try:
        with socket.create_connection((host,port),timeout=2):
            print(f"port_{port}=LISTENING")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"port {port} failed to start")
PY
}

tmux new-session -d -s trace-net-cognitive-8118 \
  "bash /tmp/start_trace_net_cognitive_8118.sh 2>&1 | tee '$RUNTIME/8118.log'"
wait_port 127.0.0.1 8118

tmux new-session -d -s trace-net-gemma-cognitive-8128 \
  "bash /tmp/start_trace_net_gemma_cognitive_8128.sh 2>&1 | tee '$RUNTIME/8128.log'"
wait_port 127.0.0.1 8128

tmux new-session -d -s trace-net-openwebui-cognitive-8131 \
  "bash /tmp/start_trace_net_openwebui_cognitive_8131.sh 2>&1 | tee '$RUNTIME/8131.log'"
wait_port "$BRIDGE_HOST" 8131

# If docker0 uses a non-default address, verify that exact address too.
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: verify the live router received the requested mode.
curl --fail-with-body --silent --show-error \
  http://127.0.0.1:8118/health \
  > "$RUNTIME/8118_health.json"
"$PYTHON" -m json.tool "$RUNTIME/8118_health.json"
"$PYTHON" - "$RUNTIME/8118_health.json" "$PLANNER_ROLLOUT_MODE" "$PLANNER_EXECUTION_ENABLED" <<'PY'
import json
import sys
from pathlib import Path

filename, requested_mode, raw_enabled = sys.argv[1:]
health = json.loads(Path(filename).read_text(encoding="utf-8"))
requested_enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
expected_execution = requested_enabled and requested_mode != "validate_only"
actual_mode = str(health.get("planner_rollout_mode") or "")
actual_execution = bool(health.get("planner_execution_enabled"))
phase_by_mode = {"validate_only": 2, "narrow": 3, "broad": 4, "mature": 5}
actual_phase = health.get("planner_rollout_phase")
expected_phase = phase_by_mode[requested_mode]

print(f"requested_planner_mode={requested_mode}")
print(f"live_planner_mode={actual_mode}")
print(f"expected_planner_execution={str(expected_execution).lower()}")
print(f"live_planner_execution={str(actual_execution).lower()}")
print(f"expected_planner_phase={expected_phase}")
print(f"live_planner_phase={actual_phase}")

failures = []
if actual_mode != requested_mode:
    failures.append(f"mode:{actual_mode}!={requested_mode}")
if actual_execution is not expected_execution:
    failures.append(f"execution:{actual_execution}!={expected_execution}")
if actual_phase != expected_phase:
    failures.append(f"phase:{actual_phase}!={expected_phase}")
if failures:
    raise SystemExit("planner launcher environment mismatch: " + ", ".join(failures))
print("planner_launcher_env_check=PASS")
PY
curl --fail-with-body --silent --show-error http://127.0.0.1:8128/health | "$PYTHON" -m json.tool
curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" | "$PYTHON" -m json.tool

echo
echo "============================================================"
echo "VERIFYING ALL 19 ROUTES WITHOUT EXPENSIVE RETRIEVAL"
echo "============================================================"

"$PYTHON" scripts/benchmark/run_trace_net_cognitive_route_smoke_v1.py \
  --base-url http://127.0.0.1:8118 \
  --api-key "$COGNITIVE_KEY" \
  --output "$RUNTIME/all_route_plan_smoke.json"
# TRACE_NET_H30_CRITICAL_LIVE_ROUTE_SMOKE_SWITCH_V1
if [[ "$RUN_CRITICAL_LIVE_ROUTE_SMOKE" == "1" ]]; then

echo
echo "============================================================"
echo "RUNNING FIVE CRITICAL LIVE ROUTE TESTS"
echo "============================================================"

"$PYTHON" scripts/benchmark/run_trace_net_cognitive_route_smoke_v1.py \
  --base-url http://127.0.0.1:8118 \
  --api-key "$COGNITIVE_KEY" \
  --timeout-seconds 1200 \
  --live \
  --output "$RUNTIME/critical_live_route_smoke.json"
else
  echo
  echo "============================================================"
  echo "SKIPPING FIVE CRITICAL LIVE ROUTE TESTS"
  echo "============================================================"
  echo "TRACE_NET_RUN_CRITICAL_LIVE_ROUTE_SMOKE=0"
  echo "Enable only for router/retrieval/release gates."
fi

echo
echo "============================================================"
echo "TESTING OPENWEBUI-COMPATIBLE SSE FROM HOST"
echo "============================================================"

curl --fail-with-body --silent --show-error --no-buffer --max-time 1200 \
  "http://$BRIDGE_HOST:8131/v1/chat/completions" \
  -H "Authorization: Bearer $PUBLIC_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$PUBLIC_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}],\"stream\":true,\"temperature\":0}" \
  > "$RUNTIME/openwebui_stream_test.txt"

grep -Fq 'chat.completion.chunk' "$RUNTIME/openwebui_stream_test.txt"
grep -Fq 'data: [DONE]' "$RUNTIME/openwebui_stream_test.txt"
echo "HOST_STREAM_TEST=PASS"

echo
echo "============================================================"
echo "TESTING FROM INSIDE OPENWEBUI CONTAINER"
echo "============================================================"

docker exec -i \
  -e TRACE_NET_URL="http://$BRIDGE_HOST:8131/v1/chat/completions" \
  -e TRACE_NET_KEY="$PUBLIC_KEY" \
  -e TRACE_NET_MODEL="$PUBLIC_MODEL" \
  open-webui \
  python - <<'PY'
import json, os, urllib.request
payload={
  "model":os.environ["TRACE_NET_MODEL"],
  "messages":[{"role":"user","content":"hello"}],
  "stream":True,
  "temperature":0,
}
request=urllib.request.Request(
  os.environ["TRACE_NET_URL"],
  data=json.dumps(payload).encode(),
  headers={"Authorization":"Bearer "+os.environ["TRACE_NET_KEY"],"Content-Type":"application/json"},
  method="POST",
)
with urllib.request.urlopen(request,timeout=1200) as response:
  content_type=response.headers.get("Content-Type","")
  text=response.read().decode("utf-8",errors="replace")
assert "text/event-stream" in content_type
assert "chat.completion.chunk" in text
assert "data: [DONE]" in text
print("OPENWEBUI_CONTAINER_STREAM_TEST=PASS")
PY

cat > "$RUNTIME/openwebui_connection.json" <<JSON
{
  "base_url": "http://$BRIDGE_HOST:8131/v1",
  "api_key": "$PUBLIC_KEY",
  "model": "$PUBLIC_MODEL",
  "cognitive_router": "http://127.0.0.1:8118",
  "gemma_writer": "http://127.0.0.1:8128",
  "route_count": 19,
  "self_rag": true,
  "crag": true,
  "direct_evidence_only_gemma_writing": true,
  "post_answer_validation": true,
  "gemma_preload": true,
  "gemma_keep_alive": "$GEMMA_KEEP_ALIVE",
  "streaming_mode": "upstream_sse_with_validated_answer_release",
  "raw_unvalidated_tokens_exposed": false
}
JSON

echo
echo "============================================================"
echo "TRACE-NET H30 COGNITIVE OPENWEBUI STACK READY"
echo "============================================================"
echo
echo "Base URL:"
echo "  http://$BRIDGE_HOST:8131/v1"
echo
echo "API key:"
echo "  $PUBLIC_KEY"
echo
echo "Model:"
echo "  $PUBLIC_MODEL"
echo
echo "Gemma keep-alive:"
echo "  $GEMMA_KEEP_ALIVE"
echo
echo "Streaming mode:"
echo "  upstream SSE with validated answer release"
echo
echo "Connection file:"
echo "  $RUNTIME/openwebui_connection.json"
echo
echo "Existing 8130 stack was not changed."
