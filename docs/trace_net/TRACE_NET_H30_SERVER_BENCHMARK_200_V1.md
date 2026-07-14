# TRACE-Net H30 Server Benchmark 200 v1

## Purpose

This patch adds a read-only 200-question full-stack server benchmark for the
H30 cognitive TRACE-Net stack. It calls the validated Gemma endpoint on port
8128 and prints immediate progress from `[001/200]` through `[200/200]`.

The 200-question bank is embedded in the runner. The patch does not add files to
`local_data` and does not package generated outputs or source artifacts.

## Coverage

Every H30 route receives at least ten planned questions. The benchmark also
exercises the existing normal source route, guided discovery, visual retrieval,
table/IPL, OCR, graph and semantic guidance, Self-RAG, CRAG, Gemma validation,
deterministic fallback, and clarification behavior.

A response is not considered successful merely because HTTP and routing pass.
Each result is independently graded for:

- clue satisfaction;
- strict alphanumeric prefix, contains, and suffix fidelity;
- candidate validity and unrelated-fallback rejection;
- OCR and navigation-garbage rejection;
- requested-field relevance;
- citation alignment to direct evidence;
- source-support and guidance-only boundaries;
- follow-up-question deduplication;
- route and retrieval-tunnel preservation;
- explicit authority for approval, fit, interchangeability, effectivity,
  eligibility, applicability, and installation claims;
- all answer and source-mutation permission flags remaining exactly false.

## Installed files

- `scripts/run_trace_net_h30_server_benchmark_200_v1.py`
- `scripts/launch_trace_net_h30_server_benchmark_200_v1.sh`
- `tests/unit/test_trace_net_h30_server_benchmark_200_v1.py`
- `docs/trace_net/TRACE_NET_H30_SERVER_BENCHMARK_200_V1.md`

## Outputs

The default server output directory is:

```text
/data/trace_net_runs/cognitive_benchmark_200_v1_answer_quality/
```

The benchmark writes:

- `trace_net_h30_server_benchmark_200_v1.json` — final report containing every
  question, answer, follow-up question, route, tunnel, evidence count, critic,
  repair, post-answer validation, semantic grading dimension, and timing;
- `trace_net_h30_server_benchmark_200_v1.jsonl` — one record per completed
  question;
- `trace_net_h30_server_benchmark_200_v1_checkpoint.json` — atomic resume
  checkpoint after every completed question;
- `trace_net_h30_server_benchmark_200_v1_console.log` — visible progress log.

## Safety contract

The benchmark is inference-only and read-only. It never writes to PostgreSQL,
Qdrant, OpenSearch, source-truth artifacts, or manual artifacts. Candidate,
semantic, visual, graph, and summary records remain guidance until resolved to
direct citation-ready evidence.

The benchmark requires these values to remain exactly false:

```text
answer_permission
final_answer_allowed
can_answer_directly
can_prove_claims
source_truth_mutation_allowed
```

## Deployment sequence

Apply and test on the Windows laptop first. Commit and push only after compile,
focused pytest, nearby regression tests, and diff inspection pass. Pull the exact
commit into the Ubuntu H30 canary worktree, rerun tests, then launch the full
benchmark in tmux. No live service restart is required because this patch only
adds benchmark tooling.

## Windows installer portability

`APPLY_ME.py` does not invoke `bash` through Windows Python. On Windows, the
`bash` executable name can resolve to the WSL relay even when the command was
launched from Git Bash. The installer performs deterministic static validation
and Python compilation transactionally; operators then run `bash -n` explicitly
from Git Bash as the shell-syntax gate.
