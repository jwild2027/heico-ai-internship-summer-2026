# TRACE-Net NHA Phases N0–N3

This package builds a read-only pilot relationship bundle from a TIFF manual.

## Included phases

- **N0:** Parse METS `metadata.xml` and map every TIFF to its canonical page ID.
- **N1:** Find source-backed assembly anchors in figure/IPL titles.
- **N2:** Reconstruct exact OCR IPL rows while preserving item, part, nomenclature, quantity, and attaching-parts state.
- **N3:** Build initial `AssemblyMembership` records and a benchmark answer key.

## Conservative relationship rules

- A single explicit parent assembly plus an exact IPL child row can produce a `source_supported` direct relationship.
- A slash-group title with several parent variants remains `ambiguous` until usage-code/effectivity resolution is implemented.
- Rows inside an unresolved `ATTACHING PARTS` block remain `candidate` relationships until Phase N4.
- Only `source_supported` memberships generate `DIRECT_COMPONENT_OF` and `HAS_DIRECT_COMPONENT` convenience edges.
- No synthetic records are created in N0–N3 because the supplied manual contains real assembly/IPL evidence.

## Safety contract

The builder writes JSON files only. It performs no Postgres, Qdrant, OpenSearch, or production graph writes. It makes no LLM call and never promotes ambiguous relationships to proof.

## Default pilot pages

`342-344,348-349,351,354,363,368`

These pages include real seat-structure figure titles and IPL rows around parts such as `120-29067-001`, `120-29067-003/021/031`, and `120-29068-001`.
