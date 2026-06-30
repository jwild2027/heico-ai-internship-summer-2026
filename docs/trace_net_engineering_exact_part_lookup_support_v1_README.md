# TRACE-Net Engineering Exact Part Lookup Support v1

H7A expands the engineering answer context/composer path so `exact_part_lookup` questions can use source-trace-ready exact/table evidence, OCR-backed nomenclature, and any linked visual evidence already present.

The patch keeps v2 summaries as guidance only. It does not permit answer permission, source-truth mutation, or external writes.

## Main behavior

- Adds `exact_part_evidence` proof-context records for requested part numbers found in trusted table/exact artifacts.
- Preserves `table_ocr_proof`, `ocr_nomenclature`, and `visual_figure_link` evidence when available.
- Updates the composer so exact-part questions answer in part-first language rather than figure-first language.
- Keeps unsupported claims such as interchangeability, effectivity, fit, replacement approval, and installation safety forbidden unless explicitly proven.

## Expected use

Run the H5 engineering answer runner for an exact part query, for example:

```bash
python -B scripts/build_trace_net_engineering_answer_runner_v1.py \
  --question "Find part number 120-50645-005 and cite the source." \
  --v2-summary-guidance-index local_data/organization/trace_net/v2_summary_guidance_index_v1/trace_net_v2_summary_guidance_index_v1.json \
  --image-visual-evidence-pack local_data/organization/trace_net/image_visual_evidence_nomenclature_merger_v1/trace_net_image_visual_evidence_pack_with_nomenclature_v1.json \
  --raw-ocr-nomenclature-extractor local_data/organization/trace_net/raw_ocr_nomenclature_window_extractor_v1/trace_net_raw_ocr_nomenclature_window_extractor_v1.json \
  --table-route-evidence-packager local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json \
  --table-exact-search-adapter local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json \
  --output-dir local_data/organization/trace_net/engineering_answer_runner_v1_exact_part_120_50645_005
```

## Safety

- Postgres writes: disabled
- Qdrant writes: disabled
- OpenSearch writes/uploads: disabled
- source-truth mutation: disabled
- answer permission: false
