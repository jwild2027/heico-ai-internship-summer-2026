# TRACE-Net Table Full-Enclosure BBox Overlay Export v1

This module exports PNG overlays and a contact sheet for `trace_net_table_full_enclosure_bbox_reconstructor_v1`.

It is intended as a human QA stage after the conservative full-table enclosure reconstruction pass. The overlay colors are:

- amber: upstream/input bbox
- blue: accepted visual candidate, when present
- red: rejected visual candidate, when present
- green: final full-table enclosure bbox

The module is read-only with respect to TRACE-Net source truth and services. It writes only local artifacts under the requested output directory. It does not write to Postgres, Qdrant, OpenSearch, or any source-truth store. It grants no answer permission and no claim-proof authority.

## Build

```bash
python scripts/build_trace_net_table_full_enclosure_bbox_overlay_export_v1.py \
  --table-full-enclosure-bbox-reconstructor local_data/organization/trace_net/table_full_enclosure_bbox_reconstructor/trace_net_table_full_enclosure_bbox_reconstructor_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_full_enclosure_bbox_overlay_export \
  --quality
```

## Output

- `trace_net_table_full_enclosure_bbox_overlay_export_v1.json`
- `trace_net_table_full_enclosure_bbox_overlay_export_v1_records.jsonl`
- `trace_net_table_full_enclosure_bbox_overlay_export_v1_summary.json`
- `trace_net_table_full_enclosure_bbox_overlay_export_v1_quality.json`
- `trace_net_table_full_enclosure_bbox_overlay_contact_sheet_v1.png`
- `overlays/*.png`


## Step-0 full-page bbox compatibility

This overlay exporter now counts `final_table_bbox_source=full_page_table_bbox` as a reconstructed full-enclosure overlay and reports `full_page_bbox_overlay_count`, so temporary whole-page table extraction overlays can pass quality checks without being mislabeled as passthrough.
