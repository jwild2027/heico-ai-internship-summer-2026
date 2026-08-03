#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-/data/trace_net/repos/heico-ai-internship-summer-2026}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="$VENV/bin/python"
RUNTIME="${TRACE_NET_RUNTIME_DIR:-/data/trace_net_runs/gemma_residency_watchdog_v2}"
BRIDGE_HOST="${TRACE_NET_BRIDGE_HOST:-172.17.0.1}"
COGNITIVE_URL="${TRACE_NET_COGNITIVE_URL:-http://127.0.0.1:8118}"
COGNITIVE_KEY="${TRACE_NET_COGNITIVE_KEY:-trace-net-cognitive-local}"
WRITER_KEY="${TRACE_NET_GEMMA_COGNITIVE_KEY:-trace-net-gemma-cognitive-local}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
GEMMA_KEEP_ALIVE="${TRACE_NET_GEMMA_KEEP_ALIVE:-1h}"
CHECK_INTERVAL="${TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS:-300}"
RENEW_BEFORE="${TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS:-900}"
PRELOAD_TIMEOUT="${TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS:-300}"
REQUIRE_RESIDENT="${TRACE_NET_GEMMA_REQUIRE_RESIDENT:-1}"
WATCHDOG_ENABLED="${TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED:-1}"
WRITER_QUEUE_TIMEOUT="${TRACE_NET_GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS:-120}"
PUBLIC_TIMEOUT="${TRACE_NET_PUBLIC_PROXY_TIMEOUT_SECONDS:-360}"
GEMMA_TIMEOUT="${TRACE_NET_PUBLIC_GEMMA_TIMEOUT_SECONDS:-240}"
GEMMA_MAX_TOKENS="${TRACE_NET_PUBLIC_GEMMA_MAX_TOKENS:-512}"
PHASE4_DIR="${TRACE_NET_NHA_PHASE4_DIR:-$REPO/release_data/trace_net/nha_real_release_v1/phase4}"
NHA_ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
TELEMETRY_PATH="${TRACE_NET_NHA_TELEMETRY_PATH:-$RUNTIME/8131_residency_telemetry.jsonl}"

RUN_FOCUSED_TESTS="${TRACE_NET_GEMMA_LAUNCHER_RUN_FOCUSED_TESTS:-1}"
RUN_PROGRESS_SMOKE="${TRACE_NET_GEMMA_LAUNCHER_RUN_PROGRESS_SMOKE:-1}"

# Full validated writer configuration. Each value remains explicitly
# overridable, but the health gate refuses a reduced production writer.
ENGRAM_SKILL_SHADOW_ENABLED="${TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED:-1}"
ENGRAM_SKILL_CARDS_PATH="${TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH:-$REPO/local_data/organization/trace_net/engram_skill_cards_v1/trace_net_engram_skill_cards_v1.json}"
ENGRAM_SKILL_SHADOW_MAX_SKILLS="${TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS:-3}"
EVIDENCE_AWARE_ANSWER_MODES_ENABLED="${TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED:-1}"
EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS="${TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS:-6}"
FINAL_ENGRAM_ROLLOUT_ENABLED="${TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED:-1}"
FINAL_ENGRAM_MAX_FOLLOWUPS="${TRACE_NET_H30_FINAL_ENGRAM_MAX_FOLLOWUPS:-3}"
FINAL_ENGRAM_MAX_REPAIRS="${TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS:-1}"
EVIDENCE_SYNTHESIS_ENABLED="${TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED:-1}"
CONSTRAINED_WRITER_ENABLED="${TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED:-1}"
CONSTRAINED_WRITER_ROUTES="${TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES:-exact_identifier_lookup,exact_table_ipl_lookup,ata_system_discovery}"
CONSTRAINED_WRITER_MAX_CITATIONS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS:-16}"
CONSTRAINED_WRITER_MAX_OUTPUT_CHARS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS:-12000}"
CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS="${TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS:-1}"
CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS:-45}"
CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS:-210}"
CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS:-20}"
CONSTRAINED_WRITER_MIN_CALL_SECONDS="${TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS:-8}"
CONSTRAINED_WRITER_MAX_TOKENS="${TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS:-512}"
PHASE19_PRESERVATION_WRITER_ENABLED="${TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED:-0}"
PHASE19_PRESERVATION_MAX_TOKENS="${TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS:-384}"
WRITER_TIMEOUT="${TRACE_NET_GEMMA_WRITER_TIMEOUT_SECONDS:-$CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS}"

validate_switch() {
  local name="$1"
  local value="$2"
  if [[ "$value" != "0" && "$value" != "1" ]]; then
    echo "invalid_boolean_switch=${name}:${value}"
    exit 2
  fi
}
validate_switch TRACE_NET_GEMMA_LAUNCHER_RUN_FOCUSED_TESTS "$RUN_FOCUSED_TESTS"
validate_switch TRACE_NET_GEMMA_LAUNCHER_RUN_PROGRESS_SMOKE "$RUN_PROGRESS_SMOKE"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for required in \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py \
  scripts/trace_net_h30_gemma_residency_watchdog_v2.py \
  tests/unit/test_trace_net_h30_gemma_residency_watchdog_v2.py \
  tests/unit/test_trace_net_gemma_residency_launcher_v2_1.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 2; }
done

[[ -d "$PHASE4_DIR" ]] || { echo "missing_phase4_dir=$PHASE4_DIR"; exit 2; }
[[ -d "$NHA_ENGRAM_DIR" ]] || { echo "missing_nha_engram_dir=$NHA_ENGRAM_DIR"; exit 2; }

for command in curl tmux timeout ss pgrep; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 2; }
done

echo "============================================================"
echo "TRACE-NET GEMMA RESIDENCY LAUNCHER V2.1"
echo "============================================================"
echo "repo=$REPO"
echo "runtime=$RUNTIME"
echo "model=$GEMMA_MODEL"
echo "keep_alive=$GEMMA_KEEP_ALIVE"
echo "watchdog_interval_seconds=$CHECK_INTERVAL"
echo "renew_before_seconds=$RENEW_BEFORE"

echo
echo "=== 1. Verify existing cognitive router ==="
curl --fail-with-body --silent --show-error \
  "$COGNITIVE_URL/health" \
  | tee "$RUNTIME/8118_health_before.json" \
  | "$PYTHON" -m json.tool

if [[ "$RUN_FOCUSED_TESTS" == "1" ]]; then
  echo
  echo "=== 2. Compile and run focused launcher/residency tests ==="
  "$PYTHON" -m py_compile \
    scripts/trace_net_h30_gemma_residency_watchdog_v2.py \
    scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py \
    scripts/serve_trace_net_full_gemma_cognitive_v1.py \
    tests/unit/test_trace_net_h30_gemma_residency_watchdog_v2.py \
    tests/unit/test_trace_net_gemma_residency_launcher_v2_1.py
  bash -n \
    scripts/launch_trace_net_gemma_resident_openwebui_v2.sh \
    scripts/launch_trace_net_gemma_resident_openwebui_v2_1.sh
  "$PYTHON" -m pytest -q -p no:cacheprovider \
    tests/unit/test_trace_net_h30_gemma_residency_watchdog_v2.py \
    tests/unit/test_trace_net_gemma_residency_launcher_v2_1.py
  echo "focused_test_status=PASS"
else
  echo
  echo "=== 2. Focused tests skipped by explicit launcher switch ==="
fi

echo
echo "=== 3. Preload and verify Gemma residency ==="
"$PYTHON" - "$GEMMA_MODEL" "$GEMMA_KEEP_ALIVE" "$PRELOAD_TIMEOUT" "$RUNTIME/preload.json" <<'PY'
from pathlib import Path
import json
import sys
import time
import urllib.request

model, keep_alive, timeout, output = sys.argv[1:]
payload = {
    "model": model,
    "prompt": "",
    "stream": False,
    "keep_alive": keep_alive,
}
request = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.monotonic()
with urllib.request.urlopen(request, timeout=float(timeout)) as response:
    body = json.loads(response.read().decode("utf-8", errors="replace"))
preload_ms = round((time.monotonic() - started) * 1000.0, 3)
body["preload_ms"] = preload_ms
body["requested_keep_alive"] = keep_alive
Path(output).write_text(json.dumps(body, indent=2), encoding="utf-8")
print("gemma_preload_status=PASS")
print(f"gemma_preload_ms={preload_ms}")
PY

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:11434/api/ps \
  > "$RUNTIME/ollama_ps_after_preload.json"

"$PYTHON" - "$GEMMA_MODEL" "$RUNTIME/ollama_ps_after_preload.json" <<'PY'
from pathlib import Path
import json
import sys
model, path = sys.argv[1:]
data = json.loads(Path(path).read_text(encoding="utf-8"))
rows = [row for row in data.get("models") or [] if isinstance(row, dict)]
names = {str(row.get("name") or row.get("model") or "") for row in rows}
print("ollama_loaded_models=" + ",".join(sorted(names)))
if model not in names:
    raise SystemExit(f"gemma_resident_status=FAIL missing={model}")
row = next(row for row in rows if str(row.get("name") or row.get("model") or "") == model)
print("gemma_resident_status=PASS")
print(f"gemma_resident_expires_at={row.get('expires_at')}")
print(f"gemma_size_vram={row.get('size_vram')}")
PY

WRITER_SESSION="trace-net-gemma-cognitive-8128"
PROXY_SESSION="trace-net-openwebui-cognitive-8131"
WRITER_PORT="8128"
PROXY_PORT="8131"
WRITER_PATTERN='[s]erve_trace_net_full_gemma_cognitive_v1.py.*--port[[:space:]]+8128'
PROXY_PATTERN_V1_1='[s]erve_trace_net_nha_phase16_gemma_proxy_v1_1.py.*--port[[:space:]]+8131'
PROXY_PATTERN_V1='[s]erve_trace_net_nha_phase16_gemma_proxy_v1.py.*--port[[:space:]]+8131'

q() {
  printf '%q' "$1"
}

port_listener_lines() {
  local port="$1"
  ss -ltnpH 2>/dev/null | awk -v suffix=":${port}" '$4 ~ (suffix "$") {print}'
}

port_is_listening() {
  [[ -n "$(port_listener_lines "$1")" ]]
}

matching_pids() {
  local pattern="$1"
  pgrep -f -- "$pattern" 2>/dev/null || true
}

terminate_exact_pattern() {
  local label="$1"
  local pattern="$2"
  local -a pids=()
  local -a remaining=()

  mapfile -t pids < <(matching_pids "$pattern")
  if [[ "${#pids[@]}" -eq 0 ]]; then
    echo "${label}_process=not_running"
    return 0
  fi

  echo "${label}_term_pids=${pids[*]}"
  kill -TERM "${pids[@]}" 2>/dev/null || true

  for _ in $(seq 1 20); do
    sleep 0.25
    mapfile -t remaining < <(matching_pids "$pattern")
    if [[ "${#remaining[@]}" -eq 0 ]]; then
      echo "${label}_term_status=PASS"
      return 0
    fi
  done

  echo "${label}_kill_pids=${remaining[*]}"
  kill -KILL "${remaining[@]}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    sleep 0.2
    mapfile -t remaining < <(matching_pids "$pattern")
    if [[ "${#remaining[@]}" -eq 0 ]]; then
      echo "${label}_kill_status=PASS"
      return 0
    fi
  done

  echo "${label}_stop_status=FAIL remaining=${remaining[*]}"
  return 1
}

stop_exact_service() {
  local label="$1"
  local session="$2"
  local port="$3"
  shift 3
  local pattern

  echo "stopping_service=${label}"
  timeout 5s tmux kill-session -t "$session" 2>/dev/null || true

  for pattern in "$@"; do
    terminate_exact_pattern "$label" "$pattern"
  done

  for _ in $(seq 1 20); do
    if ! port_is_listening "$port"; then
      echo "${label}_port_clear=PASS"
      return 0
    fi
    sleep 0.25
  done

  echo "${label}_port_clear=FAIL port=${port}"
  port_listener_lines "$port" || true
  echo "Refusing broad port kill; inspect the unexpected listener above."
  return 1
}

echo
echo "=== 4. Safely restart only proxy 8131 and writer 8128 ==="
# Stop the public entry point first so no request reaches a writer being restarted.
stop_exact_service proxy_8131 "$PROXY_SESSION" "$PROXY_PORT" \
  "$PROXY_PATTERN_V1_1" "$PROXY_PATTERN_V1"
stop_exact_service writer_8128 "$WRITER_SESSION" "$WRITER_PORT" \
  "$WRITER_PATTERN"

WRITER_START="$RUNTIME/start_writer_8128_v2_1.sh"
PROXY_START="$RUNTIME/start_proxy_8131_v2_1.sh"

cat > "$WRITER_START" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(q "$REPO")
source $(q "$VENV/bin/activate")
export PYTHONPATH=$(q "$REPO/scripts:$REPO")
export TRACE_NET_GEMMA_KEEP_ALIVE=$(q "$GEMMA_KEEP_ALIVE")
export TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED=$(q "$WATCHDOG_ENABLED")
export TRACE_NET_GEMMA_REQUIRE_RESIDENT=$(q "$REQUIRE_RESIDENT")
export TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS=$(q "$CHECK_INTERVAL")
export TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS=$(q "$RENEW_BEFORE")
export TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS=$(q "$PRELOAD_TIMEOUT")
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED=$(q "$ENGRAM_SKILL_SHADOW_ENABLED")
export TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH=$(q "$ENGRAM_SKILL_CARDS_PATH")
export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS=$(q "$ENGRAM_SKILL_SHADOW_MAX_SKILLS")
export TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED=$(q "$EVIDENCE_AWARE_ANSWER_MODES_ENABLED")
export TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS=$(q "$EVIDENCE_AWARE_ANSWER_MODES_MAX_ITEMS")
export TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED=$(q "$FINAL_ENGRAM_ROLLOUT_ENABLED")
export TRACE_NET_H30_FINAL_ENGRAM_MAX_FOLLOWUPS=$(q "$FINAL_ENGRAM_MAX_FOLLOWUPS")
export TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS=$(q "$FINAL_ENGRAM_MAX_REPAIRS")
export TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED=$(q "$EVIDENCE_SYNTHESIS_ENABLED")
export TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED=$(q "$CONSTRAINED_WRITER_ENABLED")
export TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES=$(q "$CONSTRAINED_WRITER_ROUTES")
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_CITATIONS=$(q "$CONSTRAINED_WRITER_MAX_CITATIONS")
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_OUTPUT_CHARS=$(q "$CONSTRAINED_WRITER_MAX_OUTPUT_CHARS")
export TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS=$(q "$CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS")
export TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS=$(q "$CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS")
export TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS=$(q "$CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS")
export TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS=$(q "$CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS")
export TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS=$(q "$CONSTRAINED_WRITER_MIN_CALL_SECONDS")
export TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS=$(q "$CONSTRAINED_WRITER_MAX_TOKENS")
export TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=$(q "$PHASE19_PRESERVATION_WRITER_ENABLED")
export TRACE_NET_H30_PHASE19_PRESERVATION_MAX_TOKENS=$(q "$PHASE19_PRESERVATION_MAX_TOKENS")
exec $(q "$PYTHON") -u -B scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  --host 127.0.0.1 \
  --port 8128 \
  --cognitive-base-url $(q "$COGNITIVE_URL") \
  --cognitive-api-key $(q "$COGNITIVE_KEY") \
  --gemma-base-url http://127.0.0.1:11434/v1 \
  --gemma-api-key ollama \
  --gemma-model $(q "$GEMMA_MODEL") \
  --api-key $(q "$WRITER_KEY") \
  --timeout-seconds $(q "$WRITER_TIMEOUT") \
  --max-concurrency 1 \
  --queue-timeout-seconds $(q "$WRITER_QUEUE_TIMEOUT") \
  >>$(q "$RUNTIME/8128.log") 2>&1
EOF

cat > "$PROXY_START" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(q "$REPO")
source $(q "$VENV/bin/activate")
export PYTHONPATH=$(q "$REPO/scripts:$REPO")
export TRACE_NET_GEMMA_KEEP_ALIVE=$(q "$GEMMA_KEEP_ALIVE")
export TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED=$(q "$WATCHDOG_ENABLED")
export TRACE_NET_GEMMA_REQUIRE_RESIDENT=$(q "$REQUIRE_RESIDENT")
export TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS=$(q "$CHECK_INTERVAL")
export TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS=$(q "$RENEW_BEFORE")
export TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS=$(q "$PRELOAD_TIMEOUT")
exec $(q "$PYTHON") -u -B scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py \
  --host $(q "$BRIDGE_HOST") \
  --port 8131 \
  --mode gated \
  --phase4-dir $(q "$PHASE4_DIR") \
  --nha-engram-dir $(q "$NHA_ENGRAM_DIR") \
  --upstream-url http://127.0.0.1:8128 \
  --upstream-api-key $(q "$WRITER_KEY") \
  --public-api-key $(q "$PUBLIC_KEY") \
  --public-model $(q "$PUBLIC_MODEL") \
  --upstream-model $(q "$PUBLIC_MODEL") \
  --ollama-url http://127.0.0.1:11434 \
  --gemma-model $(q "$GEMMA_MODEL") \
  --telemetry-path $(q "$TELEMETRY_PATH") \
  --timeout-seconds $(q "$PUBLIC_TIMEOUT") \
  --gemma-timeout-seconds $(q "$GEMMA_TIMEOUT") \
  --gemma-max-tokens $(q "$GEMMA_MAX_TOKENS") \
  >>$(q "$RUNTIME/8131.log") 2>&1
EOF

chmod 700 "$WRITER_START" "$PROXY_START"
bash -n "$WRITER_START" "$PROXY_START"

tmux new-session -d -s "$WRITER_SESSION" "$WRITER_START"

wait_health() {
  local label="$1"
  local url="$2"
  local output="$3"
  local log_path="$4"
  local mode="$5"

  for _ in $(seq 1 60); do
    if curl --silent --show-error --max-time 10 "$url" > "$output" 2>/dev/null; then
      if "$PYTHON" - "$output" "$mode" <<'PY' >/dev/null 2>&1
from pathlib import Path
import json
import sys

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
mode = sys.argv[2]
common = (
    data.get("quality_status") == "PASS"
    and data.get("gemma_model_resident") is True
    and data.get("cold_start_risk") is False
    and data.get("gemma_residency_watchdog_running") is True
)
if mode == "writer":
    healthy = common and all((
        data.get("evidence_aware_answer_modes_enabled") is True,
        data.get("final_engram_rollout_enabled") is True,
        data.get("constrained_gemma_writer_enabled") is True,
        data.get("legacy_freeform_writer_suppressed") is True,
        data.get("phase3_deterministic_fallback_preserved") is True,
    ))
elif mode == "proxy":
    healthy = common and all((
        data.get("upstream_ready") is True,
        data.get("validated_progress_streaming") is True,
        data.get("raw_unvalidated_tokens_exposed") is False,
    ))
else:
    healthy = False
raise SystemExit(0 if healthy else 1)
PY
      then
        echo "${label}_health=PASS"
        return 0
      fi
    fi
    sleep 2
  done

  echo "${label}_health=FAIL"
  [[ -f "$output" ]] && "$PYTHON" -m json.tool < "$output" || true
  [[ -f "$log_path" ]] && tail -n 120 "$log_path" || true
  tmux capture-pane -p -t "$label" 2>/dev/null | tail -n 80 || true
  return 1
}

wait_health "$WRITER_SESSION" http://127.0.0.1:8128/health \
  "$RUNTIME/8128_health.json" "$RUNTIME/8128.log" writer

tmux new-session -d -s "$PROXY_SESSION" "$PROXY_START"
wait_health "$PROXY_SESSION" "http://$BRIDGE_HOST:8131/health" \
  "$RUNTIME/8131_health.json" "$RUNTIME/8131.log" proxy

echo
echo "=== 5. Enforce full writer and public health contracts ==="
"$PYTHON" - "$RUNTIME/8128_health.json" "$RUNTIME/8131_health.json" <<'PY'
from pathlib import Path
import json
import sys

writer = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
proxy = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

writer_expected = {
    "quality_status": "PASS",
    "gemma_model_resident": True,
    "cold_start_risk": False,
    "gemma_residency_watchdog_running": True,
    "evidence_aware_answer_modes_enabled": True,
    "final_engram_rollout_enabled": True,
    "constrained_gemma_writer_enabled": True,
    "legacy_freeform_writer_suppressed": True,
    "phase3_deterministic_fallback_preserved": True,
}
proxy_expected = {
    "quality_status": "PASS",
    "upstream_ready": True,
    "gemma_model_resident": True,
    "cold_start_risk": False,
    "validated_progress_streaming": True,
    "raw_unvalidated_tokens_exposed": False,
}

failures = []
for label, data, expected in (
    ("writer", writer, writer_expected),
    ("proxy", proxy, proxy_expected),
):
    print()
    print(label)
    for key, required in expected.items():
        actual = data.get(key)
        print(f"{key}={actual}")
        if actual != required:
            failures.append(f"{label}:{key}={actual!r}!={required!r}")
if failures:
    raise SystemExit("FULL_HEALTH_GATE=FAIL " + "; ".join(failures))
print()
print("FULL_HEALTH_GATE=PASS")
PY

if [[ "$RUN_PROGRESS_SMOKE" == "1" ]]; then
  echo
  echo "=== 6. Verify safe early progress SSE ==="
  curl --fail-with-body --silent --show-error --no-buffer --max-time "$PUBLIC_TIMEOUT" \
    "http://$BRIDGE_HOST:8131/v1/chat/completions" \
    -H "Authorization: Bearer $PUBLIC_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$PUBLIC_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"What bigger assembly is 120-20970-001 installed inside? Use TRACE-Net evidence and cite pages.\"}],\"temperature\":0,\"max_tokens\":128,\"stream\":true}" \
    > "$RUNTIME/progress_stream_test.txt"

  grep -Fq '"object": "trace_net.progress"' "$RUNTIME/progress_stream_test.txt"
  grep -Fq '"stage": "request_accepted"' "$RUNTIME/progress_stream_test.txt"
  grep -Fq '"stage": "gemma_resident"' "$RUNTIME/progress_stream_test.txt"
  grep -Fq '"stage": "answer_validated"' "$RUNTIME/progress_stream_test.txt"
  grep -Fq 'chat.completion.chunk' "$RUNTIME/progress_stream_test.txt"
  grep -Fq 'data: [DONE]' "$RUNTIME/progress_stream_test.txt"
  echo "SAFE_PROGRESS_STREAM_GATE=PASS"
else
  echo
  echo "=== 6. Progress smoke skipped by explicit launcher switch ==="
fi

cat > "$RUNTIME/launcher_v2_1_status.json" <<JSON
{
  "quality_status": "PASS",
  "launcher_version": "2.1",
  "writer_port": 8128,
  "public_proxy_port": 8131,
  "cognitive_router_restarted": false,
  "gemma_model": "$GEMMA_MODEL",
  "gemma_resident": true,
  "cold_start_risk": false,
  "full_writer_configuration": true,
  "safe_exact_shutdown": true,
  "broad_port_kill_used": false,
  "validated_progress_streaming": true
}
JSON

echo
echo "============================================================"
echo "TRACE-NET GEMMA RESIDENCY LAUNCHER V2.1 READY"
echo "============================================================"
echo "Base URL: http://$BRIDGE_HOST:8131/v1"
echo "API key: $PUBLIC_KEY"
echo "Model: $PUBLIC_MODEL"
echo "Runtime: $RUNTIME"
echo "Gemma resident: true"
echo "Cold-start risk: false"
echo "Full writer configuration: true"
echo "Safe exact shutdown: true"
echo "Broad port kill used: false"
echo "Validated progress streaming: true"
echo "TRACE_NET_GEMMA_RESIDENCY_LAUNCHER_V2_1=PASS"
