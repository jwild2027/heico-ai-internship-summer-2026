# TRACE-Net Graph/Baseline Checkpoint v1

This patch implements step 2 in the TRACE-Net sequence: freeze a new graph/baseline checkpoint after verifying that the graph UI exposes both part nomenclature and PageContextV2 summary tunnels.

The checkpoint is read-only. It does not mutate Postgres, graph source truth, trust tiers, RAG eligibility, feedback, citations, ranking, or generated graph explorer files.

## What it freezes

The builder writes JSON under:

```text
local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/
```

Outputs:

```text
trace_net_graph_baseline_checkpoint_v1.json
trace_net_graph_baseline_checkpoint_v1_summary.json
trace_net_graph_baseline_checkpoint_v1_manifest.json
trace_net_graph_baseline_checkpoint_v1_quality.json  # only when quality is run
```

The checkpoint captures:

- page, part, nomenclature, graph-node, and graph-edge counts
- `HAS_NOMENCLATURE` edge count
- `PageContextV2` record/page count
- `HAS_CONTEXT_V2` edge count
- required v2 coverage for pages 1-50
- graph explorer artifact checksums
- retrieval-safety baseline counts for candidate/citation/trust/evidence tables when present
- TRACE-Net boundary rules that keep ContextV2 as retrieval-helper-only

## Install from patch zip

From Git Bash at repo root:

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o /c/Users/juswil/Downloads/tracenet_graph_baseline_checkpoint_v1_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_graph_baseline_checkpoint_v1.py \
  tests/unit/test_trace_net_graph_baseline_checkpoint_v1_quality.py \
  -q
```

## Freeze the checkpoint

Make sure Postgres is running:

```bash
docker start trace-net-postgres
docker exec trace-net-postgres pg_isready -U tracenet -d tracenet_dev
```

Set the active local TRACE-Net database URL:

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"
```

Build the checkpoint and run quality gates in the same command:

```bash
python scripts/freeze_trace_net_graph_baseline_checkpoint_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --graph-explorer-dir local_data/organization/trace_net/graph_explorer \
  --output-dir local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1 \
  --checkpoint-name trace_net_graph_ui_context_v2_nomenclature_baseline_v1 \
  --require-first-pages 1-50 \
  --min-page-count 509 \
  --min-part-nodes 442 \
  --min-nomenclature-nodes 151 \
  --min-has-nomenclature-edges 386 \
  --min-context-v2-pages 50 \
  --min-has-context-v2-edges 50 \
  --require-graph-explorer-quality-pass \
  --quality
```

The exact part/nomenclature counts above match the graph UI quality output from the current checkpoint. If the graph changes intentionally later, adjust the `--min-*` gates with a new checkpoint name.

## Run quality separately

```bash
python scripts/check_trace_net_graph_baseline_checkpoint_v1_quality.py \
  --checkpoint-path local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --min-page-count 509 \
  --min-part-nodes 442 \
  --min-nomenclature-nodes 151 \
  --min-has-nomenclature-edges 386 \
  --min-context-v2-pages 50 \
  --min-has-context-v2-edges 50 \
  --require-first-pages 1-50 \
  --require-graph-explorer-quality-pass \
  --write-json
```

Expected result:

```text
TRACE-Net graph baseline checkpoint v1 quality
 Status: PASS
```

## Optional retrieval-safety gate

If the local DB has the full RAG candidate/citation baseline loaded, add stricter gates:

```bash
  --min-rag-candidates 1426 \
  --min-source-citations 1426
```

Keep these optional if you are freezing only the graph/UI context+nomenclature checkpoint.

## TRACE-Net boundary

This checkpoint preserves the current design rule:

```text
PageContextV2 = retrieval helper / query tunnel only
Part -> HAS_NOMENCLATURE -> Nomenclature = graph metadata/display path
Source citations + trust authority = answer authority
```

The next step after this checkpoint is to build `context_retrieval_helper` records from PageContextV2 while keeping `can_answer_directly = false`.
