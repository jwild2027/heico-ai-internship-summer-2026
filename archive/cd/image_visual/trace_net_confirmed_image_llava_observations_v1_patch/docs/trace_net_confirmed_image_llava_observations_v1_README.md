# TRACE-Net Confirmed Image LLaVA Observations v1

Runs LLaVA over confirmed image summary cards and writes one observation per page.

## Stage in architecture

```text
OCR / existing visual evidence
→ confirmed_image_page_summary_v1_1
→ LLaVA visual observation v1
→ final visual summary cards / retrieval docs
```

## Why this separate runner exists

The summary builder is fast and deterministic. LLaVA is slow and may fail
mid-run. This runner is resumable and appends one JSONL row per page.

## Safety

LLaVA is visual guidance only. It does not replace OCR and does not prove
fit/interchangeability/effectivity/approval/installation claims.

## Sample run

```bash
python -B scripts/build_trace_net_confirmed_image_llava_observations_v1.py \
  --confirmed-image-summary-jsonl local_data/organization/trace_net/confirmed_image_page_summary_v1_1/trace_net_confirmed_image_page_summary_v1_1.jsonl \
  --output-dir local_data/organization/trace_net/confirmed_image_llava_observations_v1_sample \
  --image-roots local_data/organization/trace_net \
  --page-ids t_p_120_1176_p000019 t_p_120_1176_p000084 t_p_120_1176_p000172 t_p_120_1176_p000446 t_p_120_1176_p000499
```

## Full run

```bash
python -B scripts/build_trace_net_confirmed_image_llava_observations_v1.py \
  --confirmed-image-summary-jsonl local_data/organization/trace_net/confirmed_image_page_summary_v1_1/trace_net_confirmed_image_page_summary_v1_1.jsonl \
  --output-dir local_data/organization/trace_net/confirmed_image_llava_observations_v1_full \
  --image-roots local_data/organization/trace_net
```
