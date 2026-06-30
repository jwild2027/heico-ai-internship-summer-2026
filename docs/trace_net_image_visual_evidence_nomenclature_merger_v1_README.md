# TRACE-Net Image Visual Evidence Nomenclature Merger v1

Merges OCR-backed nomenclature evidence from `trace_net_raw_ocr_nomenclature_window_extractor_v1` into linked image visual evidence records.

Authority contract:

- LLaVA / visual route sees and locates visual evidence.
- Trusted figure/table evidence links figure/page to part number.
- Raw OCR nomenclature windows provide official-looking part names.
- Graph/community labels are not treated as part nomenclature.
- The module writes only local artifacts and never enables answer permission.

Outputs:

- `trace_net_image_visual_evidence_nomenclature_merger_v1.json`
- `trace_net_image_visual_evidence_pack_with_nomenclature_v1.json`
- JSONL/CSV merge records
- quality check JSON
