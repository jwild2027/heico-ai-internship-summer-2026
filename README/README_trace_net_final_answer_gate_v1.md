# TRACE-Net Final Answer Gate v1

Step 12 consumes the Step 11.6 cleaned evidence snippet report and produces a
user-visible, citation-backed final answer only after a rule-based TRACE-Net
final gate passes.

The final gate authorizes answer text only when every final claim is:

- derived from `source_text_evidence` or `verified_part_evidence`;
- attached to a `page_id`;
- attached to at least one citation ID;
- authority-bearing;
- source-resolution, citation, and authority-gate required;
- free of local path leaks, raw byte wrappers, and TRACE-Net retrieval boilerplate;
- non-mutating with respect to source truth.

Retrieval-only buckets remain blocked from final claims:

- `page_retrieval_profile`
- `context_retrieval_helper`
- `source_evidence`
- `derived_context`
- raw OCR / raw visual / raw table extraction

## Gemma / Ollama support

The gate supports an optional local Ollama composer path:

```bash
--composer-mode ollama \
--llm-model "$GEMMA_MODEL" \
--ollama-url "$OLLAMA_URL"
```

Use the exact model name shown by `ollama list`, for example:

```bash
export GEMMA_MODEL="gemma4:26b"
```

The Gemma draft is advisory by default. The final answer remains the
TRACE-Net gated template unless `--allow-llm-final-text` is explicitly supplied
and the LLM draft passes citation/leak validation.

This preserves the TRACE-Net rule:

```text
LLM can help compose.
TRACE-Net gate decides what is allowed.
No citation/authority/source resolution means no final claim.
```

## Build

```bash
python scripts/build_trace_net_final_answer_gate_v1.py \
  --clean-snippets local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json \
  --output-dir local_data/organization/trace_net/final_answer_gate \
  --composer-mode ollama \
  --llm-model "$GEMMA_MODEL" \
  --ollama-url "$OLLAMA_URL" \
  --max-final-claims 8 \
  --max-claims-per-page 2 \
  --max-answer-claims 6 \
  --min-final-claims 1 \
  --require-clean-snippet-quality-pass \
  --require-clean-snippet-answer-status CLEAN_SNIPPETS_ONLY \
  --require-embedding-dim 1024 \
  --require-final-answer-allowed \
  --quality
```

For a fully deterministic run without Gemma:

```bash
python scripts/build_trace_net_final_answer_gate_v1.py \
  --clean-snippets local_data/organization/trace_net/evidence_snippet_cleaner/trace_net_evidence_snippet_cleaner_v1.json \
  --output-dir local_data/organization/trace_net/final_answer_gate \
  --composer-mode template \
  --max-final-claims 8 \
  --max-claims-per-page 2 \
  --max-answer-claims 6 \
  --min-final-claims 1 \
  --require-clean-snippet-quality-pass \
  --require-clean-snippet-answer-status CLEAN_SNIPPETS_ONLY \
  --require-embedding-dim 1024 \
  --require-final-answer-allowed \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_final_answer_gate_v1_quality.py \
  --report-path local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --min-final-claims 1 \
  --require-clean-snippet-quality-pass \
  --require-clean-snippet-answer-status CLEAN_SNIPPETS_ONLY \
  --require-embedding-dim 1024 \
  --require-final-answer-allowed \
  --write-json
```

Expected safety shape:

```text
Status: PASS
final_answer_allowed: True
uncited_final_claim_count: 0
retrieval_only_final_claim_count: 0
missing_page_id_count: 0
missing_citation_count: 0
missing_authority_count: 0
local_path_leak_count: 0
raw_bytes_repr_count: 0
boilerplate_leak_count: 0
ocr_uncertainty_note_present: True
source_truth_mutation_allowed_count: 0
llm_freeform_answer_allowed_count: 0
```

## Outputs

Generated local artifacts are written under:

```text
local_data/organization/trace_net/final_answer_gate/
```

Do not commit generated local artifacts.

Patch files to commit:

```text
tiff/trace_net_final_answer_gate_v1.py
scripts/build_trace_net_final_answer_gate_v1.py
scripts/check_trace_net_final_answer_gate_v1_quality.py
tests/unit/test_trace_net_final_answer_gate_v1.py
tests/unit/test_trace_net_final_answer_gate_v1_quality.py
tests/unit/test_trace_net_final_answer_gate_v1_script_imports.py
README_trace_net_final_answer_gate_v1.md
```
