# TRACE-Net Image Visual Summary v1 Observation Cleanup

This focused patch improves `trace_net_image_visual_summary_v1` after the first successful `llava:13b` smoke run showed prompt leakage in visual labels.

## Changes

- Tightens the LLaVA prompt to request JSON only and not repeat system/user instructions.
- Normalizes LLaVA list values into stable string arrays.
- Removes obvious prompt leakage such as `TRACE-Net's visual observer`, `You are`, and `provided in the prompt`.
- Reclassifies long non-numeric callout text into visible labels.
- Adds cleanup metadata: `prompt_leak_suspected`, `prompt_leak_removed_item_count`, `visual_observation_quality_status`, and `visual_review_reasons`.
- Adds quality-check flags for 50-page/LLaVA runs: `--min-clean-vision-observation-ready`, `--max-prompt-leak-suspected`, and `--max-review-required`.

## Safety

The artifact remains visual-observer retrieval guidance only. It grants no answer permission, does not mutate source truth, and performs no database/vector/search writes.
