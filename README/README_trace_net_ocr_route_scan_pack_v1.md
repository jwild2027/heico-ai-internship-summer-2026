# TRACE-Net OCR Route Scan Pack v1

Builds a page-by-page OCR scanner/router metadata pack from raw TIFF pages. The artifact enumerates source page images, computes hashes and image features, optionally runs Tesseract, classifies each page into a route, records route-specific scanned data kinds, and writes a one-to-one raw-TIFF comparison manifest.

Authority: scan/router metadata only. It does not grant answer permission, mutate source truth, or write to Postgres, Qdrant, or OpenSearch.
