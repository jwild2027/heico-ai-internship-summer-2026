# TIFF Real-Server Access Checklist and Runbook

Generated: `2026-06-01T12:46:37Z`
Server root placeholder: `<SERVER_ROOT>`
Target total TiB: `5.0`
Max inventory files: `100000`
Pilot pages: `500`

## Purpose

Prepare for read-only real-server inventory, OCR-depth audit, pilot OCR, and safe batched intake.

## Guardrails

- Do not run OCR, embeddings, or page-context generation across the full server on first access.
- Start with read-only inventory and OCR-depth audit using --max-files.
- Treat source TIFF locations as read-only; write derived outputs elsewhere.
- Do not store TIFF bytes in PostgreSQL, OpenSearch, or Qdrant.
- Require explicit approval before any large baseline processing run.
- Use pilot batches and quality gates before scaling.

## Checklist

### Access and permissions

- **access.server_root** (required): What is the exact read-only root path for the TIFF/ResCarta archive?
  - Why: All inventory and intake tools need a stable root path. We should not guess or crawl unrelated shares.
- **access.approved_host** (required): Which machine is approved to run read-only inventory and pilot scripts?
  - Why: The processing host determines path syntax, available disk, network speed, and whether OCR tools can be installed.
- **access.write_location** (required): Where are we allowed to write derived outputs such as OCR text, manifests, logs, and indexes?
  - Why: The source archive should stay read-only; derived data needs a separate approved location.
- **access.data_policy** (required): Are there export, retention, or access-control rules for technical manuals and derived OCR text?
  - Why: OCR text, vectors, and summaries are derived from controlled source material and may need the same access restrictions.
### Archive layout

- **layout.folder_shape** (required): What is the folder layout: one document per folder, ResCarta object folders, pages/ocr subfolders, ZIPs, or mixed?
  - Why: The scanner must group pages into documents without relying only on filenames.
- **layout.metadata_files** (required): Where are metadata files such as metadata.xml, JSON, MARC, or ResCarta descriptors stored?
  - Why: Metadata gives document IDs, titles, page order, and source-link information.
- **layout.naming** (required): Are TIFF filenames globally unique, document-local, or only page-number based?
  - Why: Our sample has duplicate stems across pages/OCR folders; production matching should use full path plus metadata.
### OCR availability

- **ocr.coverage** (required): Does the server contain full-page OCR, header-only OCR, or no OCR? Where is it stored?
  - Why: OpenSearch, Qdrant, graph extraction, and RAG require body OCR, not just headers.
- **ocr.format** (required): If OCR exists, what format is it in: plain text, ALTO XML, hOCR, PDF text layer, database field, or ResCarta export?
  - Why: Different formats need different importers and quality checks.
- **ocr.quality** (optional/planning): Do we have OCR confidence data or sample pages to compare against the TIFF images?
  - Why: OCR quality determines whether part extraction and RAG are reliable.
### ResCarta/source links

- **rescarta.deep_links** (required): What is the real ResCarta deep-link URL format for a document/page?
  - Why: The local MVP uses placeholder links. Production needs links users can open.
- **rescarta.auth** (required): Does ResCarta require authentication, VPN, cookies, or role-based access?
  - Why: The UI must show source links only to users with the right access.
### Scale and batching

- **scale.file_count** (required): Roughly how many TIFF files and total bytes are in scope?
  - Why: The cost depends on page count, not only terabytes.
- **scale.change_feed** (optional/planning): Is there a change feed, modified-time policy, or manifest that identifies new/changed pages?
  - Why: After baseline, incremental processing should avoid rescanning the full archive.
- **scale.pilot_scope** (required): Can we copy or process a small pilot set, for example 500 to 5,000 pages, before baseline?
  - Why: A pilot proves OCR/extraction/index quality before large-scale processing.
### Production storage

- **storage.postgres** (optional/planning): Where will PostgreSQL live, and who manages backups, access, and schema migrations?
  - Why: PostgreSQL will hold graph/catalog/source/feedback records.
- **storage.opensearch** (optional/planning): Where will OpenSearch live, and what index/retention limits should we assume?
  - Why: OpenSearch will hold searchable OCR/page/chunk text, which can be large.
- **storage.qdrant** (optional/planning): Where will Qdrant live, and what vector dimension/model/collection policy should we use?
  - Why: Qdrant stores embeddings and page/chunk pointers, not TIFF bytes.
### Security and audit

- **security.permissions** (required): What user/group permissions should be carried from source files into search results and graph records?
  - Why: Search and RAG must not reveal sources users cannot access.
- **security.audit_log** (optional/planning): Do we need an audit log for source opens, questions, answers, feedback, and exports?
  - Why: Technical data systems often need traceable usage history.

## First-access runbook

### 1. Confirm read-only access

Goal: Verify the approved root path and confirm scripts will only read from it.

```bash
dir <SERVER_ROOT>  # Windows, or ls <SERVER_ROOT> on Git Bash/Linux
```

Expected output: You can list the top-level source folders without permission errors.

Stop if: Access denied, path unknown, or path points to a broader share than intended.

### 2. Read-only inventory sample

Goal: Count files, measure sizes, and estimate scale without OCR/indexing.

```bash
python scripts/audit_real_server_inventory.py --root <SERVER_ROOT> --target-total-tb 5 --max-files 100000 --write-json
```

Expected output: A JSON inventory report with TIFF count, bytes, OCR count, and rough scale estimates.

Stop if: The scan sees unrelated files, too many permission errors, or unexpected file layout.

### 3. OCR-depth sample

Goal: Determine whether OCR is missing, header-only, empty, or full-page.

```bash
python scripts/audit_ocr_depth.py --root <SERVER_ROOT> --max-files 100000 --write-json --json-output local_data/ocr/real_server_ocr_depth_sample.json
```

Expected output: An OCR-depth report showing missing/header-only/full-page OCR counts.

Stop if: Most OCR is missing/header-only and no OCR-generation path is approved yet.

### 4. Document batch shape audit

Goal: Check folder shape, duplicate names, empty files, TIFF/OCR pairing, and metadata presence.

```bash
python scripts/audit_document_batch.py --root <SERVER_ROOT> --max-files 100000 --write-json
```

Expected output: A batch audit report that confirms document organization and risky files.

Stop if: Duplicate matching is ambiguous, metadata is missing, or empty TIFF/metadata files appear.

### 5. Small OCR pilot only after approval

Goal: Run OCR on a small pilot set to validate OCR quality before baseline processing.

```bash
python scripts/run_ocr_pilot.py --root <SERVER_ROOT> --limit 500 --engine auto --write-json
```

Expected output: Pilot OCR files and an OCR pilot report under local_data/ocr/pilot/.

Stop if: No OCR engine is approved/available, or pilot OCR is not good enough for extraction.

### 6. Pilot quality gate

Goal: Run source/OCR/graph/query quality checks against the pilot before scaling.

```bash
python scripts/check_full_system_quality.py --require-api-adapter-quality --require-api-contract-tests --require-user-query-tests --require-realistic-query-trace --require-source-package-traceability
```

Expected output: Quality gate is OK for the pilot/local sample.

Stop if: Any source, OCR, graph, API, or user-query check fails.

## Decision points

- If OCR is full-page and usable, import/clean it before OCR generation.
- If OCR is missing or header-only, run a controlled full-page OCR pilot.
- If TIFF count is extremely high, use selective/on-demand AI page context instead of all-page context.
- If ResCarta deep links are unknown, keep local source review links but mark real ResCarta not ready.
