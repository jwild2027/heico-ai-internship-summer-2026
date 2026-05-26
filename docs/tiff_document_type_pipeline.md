# TIFF document-type pipeline

The TIFF scanner now separates **technical scanning**, **OCR**, and **document-type parsing**.

## Flow

```text
TIFF file
  -> file/TIFF inventory
  -> local Tesseract OCR over selected regions
  -> drawing metadata parser
  -> manual/IPL metadata parser
  -> document classifier
  -> JSON report
```

## Why this was added

Not every TIFF is an engineering drawing with a title block. Some pages are maintenance manual or illustrated-parts-list pages. For those, drawing fields such as `drawing_number`, `part_number`, `revision`, and `sheet_number` may correctly remain `null`.

The scanner now adds:

```json
{
  "document_classification": {},
  "manual_metadata": {},
  "drawing_metadata": {}
}
```

## Manual/IPL fields

The manual parser tries to detect:

```text
document_type
manufacturer
manual_title
document_code
figure_title
figure_number
effectivity
ata_code
page_number
revision_date
callouts
metadata_confidence
```

For the sample Embraer manual page, expected high-value fields are:

```text
manufacturer = EMBRAER
manual_title = MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST
document_code = 120TP250002.MCE
figure_title = Double Passenger Seat
figure_number = 2
effectivity = ALL
ata_code = 25-21-00
page_number = 4
revision_date = Sep 30/98
```

## What comes next

The next improvement is a real document-class router:

```text
unknown TIFF
  -> OCR enough regions to identify the page class
  -> if engineering drawing, run title-block parser
  -> if manual/IPL page, run manual footer/header parser
  -> if form/table, run form/table parser
```

For large-scale ingestion, store both `document_classification` and the class-specific metadata in SQLite/PostgreSQL before creating search/vector indexes.
