# TRACE-Net Dublin Core Source Package Extension v1

Read-only source-package provenance extension for the refined Dublin Core page metadata.

It parses `metadata.zip` / `metadata.xml` and adds METS/MODS/TIFF package metadata to each page:

- source package label, OBJID, type, record status
- source package created date and date captured
- language code and package abstract/title
- TIFF entry name and href
- METS file ID and group ID
- TIFF size from METS and ZIP
- SHA-1 checksum from METS and computed checksum
- normalized source package page number
- source traceability status

It does not write Postgres, Qdrant, OpenSearch, graph truth, citations, or source truth.

## Build

```bash
python scripts/build_trace_net_dublin_core_source_package_extension_v1.py \
  --dublin-core-refined local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json \
  --metadata-zip /c/Users/juswil/Downloads/metadata.zip \
  --output-dir local_data/organization/trace_net/dublin_core_source_package_extension \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-pages-with-source-package-entry 509 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_dublin_core_source_package_extension_v1_quality.py \
  --report-path local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-pages-with-source-package-entry 509 \
  --require-metadata-xml \
  --write-json
```

## Safety contract

All enriched records keep:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
```

This metadata is for cataloging, provenance, incremental processing, audit, OpenSearch filtering, and page cards. It is not answer evidence.
