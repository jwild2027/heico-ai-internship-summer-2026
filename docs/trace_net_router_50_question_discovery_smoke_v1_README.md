# TRACE-Net Router 50-Question Discovery Smoke v1

This patch adds a 50-question challenge set for the TRACE-Net router/proxy v3 stack.

The goal is not to answer the questions. The goal is to test whether the system:

- routes weak/partial questions through the router correctly,
- asks useful follow-up questions,
- keeps ambiguous requests in candidate-discovery mode,
- avoids final answer permission for incomplete or safety-sensitive requests,
- keeps source-truth mutation disabled,
- preserves clean OpenAI-style response content for the web UI.

## Files

- `tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json`
  - 50 new ambiguous/safety-sensitive TRACE-Net questions.
  - Each record includes exactly 3 unanswered expected follow-up-question themes.

- `scripts/run_trace_net_router_50_question_discovery_smoke_v1.py`
  - Calls the running router endpoint at `http://127.0.0.1:8017/v1/chat/completions`.
  - Records route, quality status, assistant content, question count, and safety status.
  - Writes JSONL results, a summary JSON, and a readable report.

- `tests/unit/test_trace_net_router_50_question_discovery_smoke_v1.py`
  - Static/unit checks for the fixture and runner logic.

## Full server run

Start the router stack first:

```bash
cd ~/heico-ai-internship-summer-2026
source /home/jwild/rag-workspace/.venv/bin/activate

python3 -B scripts/launch_trace_net_router_stack_v1.py \
  --host 127.0.0.1 \
  --normal-port 8014 \
  --guided-port 8016 \
  --router-port 8017 \
  --artifact-root local_data/organization/trace_net \
  --output-root /data/trace_net_runs \
  --top-k 8 \
  --loose-top-k 8
```

Then run the 50-question smoke in a second terminal:

```bash
cd ~/heico-ai-internship-summer-2026
source /home/jwild/rag-workspace/.venv/bin/activate

python3 -B scripts/run_trace_net_router_50_question_discovery_smoke_v1.py \
  --endpoint-url http://127.0.0.1:8017/v1/chat/completions \
  --model trace-net-router-proxy-v3 \
  --questions-file tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json \
  --output-dir /data/trace_net_runs/router_50_question_discovery_smoke_v1 \
  --timeout-seconds 120
```

## Quick smoke first

Because some guided discovery calls can take around 40 seconds each, run a 5-question smoke first when debugging:

```bash
python3 -B scripts/run_trace_net_router_50_question_discovery_smoke_v1.py \
  --limit 5 \
  --output-dir /data/trace_net_runs/router_50_question_discovery_smoke_v1_quick
```

## Output files

- `/data/trace_net_runs/router_50_question_discovery_smoke_v1/router_50_question_discovery_results.jsonl`
- `/data/trace_net_runs/router_50_question_discovery_smoke_v1/summary.json`
- `/data/trace_net_runs/router_50_question_discovery_smoke_v1/router_50_question_discovery_report.txt`

## Quality policy

The runner returns:

- `PASS` if calls complete safely and every response has at least 3 assistant questions.
- `WARN` if calls are safe but some responses ask fewer than 3 questions.
- `FAIL` if there are request errors, downstream errors, answer permission violations, or source-truth mutation violations.

Routing is intentionally audited but not treated as a hard failure. This benchmark is meant to reveal which question shapes should receive future router/guided-discovery upgrades.
