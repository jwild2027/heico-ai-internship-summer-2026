# TRACE-Net Visual Question Context Gate v1

This patch integrates the calibrated meaningful image detector v1.2 with the
visual question context layer.

## Purpose

The v1.2 detector separates:

```text
image_visual
mixed_visual_table
visual_candidate_review
table
review_candidate
blank_candidate
```

This gate filters existing visual-question-context records so only confirmed
visual pages become automatic image context.

## Routing behavior

```text
image_visual          -> confirmed image context
mixed_visual_table    -> confirmed image context
visual_candidate_review -> review-only visual candidate context
table/text/blank/review -> excluded from automatic image context
```

## Inputs

- Existing visual question context JSONL, usually from:
  `visual_question_context_adapter_v1_3_full/trace_net_visual_question_context_v1_3.jsonl`
- Meaningful image detector v1.2 JSONL:
  `meaningful_image_route_detector_v1_2/trace_net_meaningful_image_route_detector_v1_2.jsonl`

## Outputs

- `trace_net_visual_question_context_gate_v1_confirmed_image_context.jsonl`
- `trace_net_visual_question_context_gate_v1_visual_candidate_review.jsonl`
- `trace_net_visual_question_context_gate_v1_excluded_context.jsonl`
- `trace_net_visual_question_context_gate_v1_missing_detector_context.jsonl`
- `summary.json`

## Safety contract

- read-only
- no Ollama calls
- no LLM calls
- no OCR execution
- no database/search/vector writes
- no source-truth mutation
- no answer permission
