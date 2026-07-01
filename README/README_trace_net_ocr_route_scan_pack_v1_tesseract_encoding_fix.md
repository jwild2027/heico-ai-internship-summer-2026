# TRACE-Net OCR Route Scan Pack v1 Tesseract Encoding Fix

Fixes a Windows subprocess decoding crash during long Tesseract OCR runs.

## Problem

`subprocess.run(..., text=True)` lets Python decode Tesseract stdout/stderr using the Windows locale codec, commonly `cp1252`. Some Tesseract output can contain bytes that `cp1252` cannot decode, causing a `UnicodeDecodeError` in Python's subprocess reader thread.

## Fix

The OCR scanner now captures Tesseract output as bytes and decodes it with a safe helper. This prevents a single undecodable byte from crashing a full 509-page scan.

## Safety

This patch does not write Postgres, Qdrant, or OpenSearch. It does not mutate source truth and grants no answer permission.
