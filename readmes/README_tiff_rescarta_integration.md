# TIFF ResCarta deep-link integration

This patch adds a configurable ResCarta deep-link layer. It does not assume the
company's final ResCarta URL format, because ResCarta-Web deployments can expose
page links with site-specific JSP routes and query parameters.

## Added files

```text
tiff/rescarta_deeplink.py
scripts/validate_rescarta_link_template.py
scripts/preview_rescarta_links.py
scripts/apply_rescarta_links.py
tests/unit/test_tiff_rescarta_deeplink.py
```

## Typical workflow

1. Get one real ResCarta page URL from the company.
2. Identify which pieces are object/document ID and page ID/page name.
3. Preview proposed URLs.
4. Apply only after preview looks correct.
5. Re-run source-link audit and quality gate.

## Example templates

Placeholder-compatible default:

```bash
--url-template "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}/{page_id}"
```

Common ResCarta-Web style with `page_name`:

```bash
--url-template "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}&page_name={page_name}&view_width=20&rotation=0"
```

Available tokens include:

```text
base_url
object_id
manual_id
manual_title
manual_slug
page_id
page_id_raw
page_name
page_label
ata_code
tiff_path
ocr_path
tiff_stem
ocr_stem
current_rescarta_url
source_url
```

## Preview

```bash
python scripts/preview_rescarta_links.py \
  --db-path local_data/db/tiff_search.db \
  --base-url "https://YOUR-RESCARTA-HOST/ResCarta-Web" \
  --url-template "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}&page_name={page_name}" \
  --show-tokens \
  --write-json
```

## Apply

Run a dry run first:

```bash
python scripts/apply_rescarta_links.py \
  --db-path local_data/db/tiff_search.db \
  --base-url "https://YOUR-RESCARTA-HOST/ResCarta-Web" \
  --url-template "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}&page_name={page_name}" \
  --dry-run
```

Apply after preview is correct:

```bash
python scripts/apply_rescarta_links.py \
  --db-path local_data/db/tiff_search.db \
  --base-url "https://YOUR-RESCARTA-HOST/ResCarta-Web" \
  --url-template "{base_url}/jsp/RcWebImageViewer.jsp?doc_id={object_id}&page_name={page_name}" \
  --confirm
```

Then rebuild/audit:

```bash
python scripts/audit_source_links.py --config local_config.yaml --strict
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py --require-incremental-smoke
```
