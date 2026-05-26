"""Streamlit TIFF upload scanner.

Run from the repo root:
    python -m streamlit run tiff_upload_scan.py

This app saves an uploaded TIFF locally, scans file/TIFF metadata, optionally
runs local Tesseract title-block OCR, writes a JSON report, and offers that JSON
for download.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.json_report import scan_tiff_to_dict, write_scan_json
from tiff.sqlite_store import connect, list_tiff_files, upsert_scan_report
from tiff.title_block_ocr import find_tesseract

UPLOAD_DIR = REPO_ROOT / "local_data" / "uploads"
JSON_DIR = REPO_ROOT / "local_data" / "json_scans"
DEFAULT_DB_PATH = REPO_ROOT / "local_data" / "tiff_scans.db"


def safe_file_name(name: str) -> str:
    """Keep uploaded filenames safe for local storage."""

    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip()
    return name or "uploaded.tif"


st.set_page_config(page_title="TIFF Upload Scan", layout="wide")
st.title("TIFF Upload Scan")
st.caption("Upload one TIFF and generate a local JSON metadata report.")

with st.sidebar:
    st.header("Scan options")
    hash_file = st.checkbox("Calculate SHA-256 hash", value=True)
    parse_filename = st.checkbox("Parse drawing metadata from filename", value=True)
    run_ocr = st.checkbox("Run local title-block OCR", value=True)
    ocr_page_index = st.number_input("OCR page index", min_value=0, max_value=1000, value=0, step=1)
    ocr_lang = st.text_input("Tesseract language", value="eng")
    tesseract_cmd = st.text_input(
        "Optional tesseract.exe path",
        value="",
        help="Leave blank to use PATH or TESSERACT_CMD. Example: C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    )
    save_uploaded_file = st.checkbox("Save uploaded TIFF under local_data/uploads", value=True)
    save_to_sqlite = st.checkbox("Save scan report to SQLite", value=True)
    db_path_text = st.text_input("SQLite DB path", value=str(DEFAULT_DB_PATH))

    detected_tesseract = find_tesseract(tesseract_cmd.strip() or None)
    if run_ocr:
        if detected_tesseract:
            st.success(f"Tesseract found: {detected_tesseract}")
        else:
            st.warning("Tesseract not found. OCR will report tesseract_not_found.")

uploaded = st.file_uploader("Choose a .tif or .tiff file", type=["tif", "tiff"])

if uploaded is None:
    st.info("Upload a TIFF to generate a JSON scan report.")
    st.stop()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

file_name = safe_file_name(uploaded.name)
upload_path = UPLOAD_DIR / file_name
upload_bytes = uploaded.getvalue()

# The current scanner expects a file path so it can read TIFF metadata with Pillow.
if save_uploaded_file:
    upload_path.write_bytes(upload_bytes)
else:
    # Still write a local temp file for scanning, but keep it in the upload folder.
    upload_path.write_bytes(upload_bytes)

try:
    report = scan_tiff_to_dict(
        upload_path,
        source_root=UPLOAD_DIR,
        hash_file=hash_file,
        parse_filename=parse_filename,
        run_ocr=run_ocr,
        ocr_page_index=int(ocr_page_index),
        ocr_lang=ocr_lang.strip() or "eng",
        tesseract_cmd=tesseract_cmd.strip() or None,
    )
except Exception as exc:
    st.error(f"Scan failed: {exc}")
    st.stop()

json_path = JSON_DIR / f"{upload_path.stem}.scan.json"
write_scan_json(report, json_path)
json_text = json.dumps(report, indent=2)

saved_db_message = None
if save_to_sqlite:
    try:
        with connect(Path(db_path_text)) as conn:
            file_id = upsert_scan_report(conn, report)
        saved_db_message = f"SQLite saved: {db_path_text} | file_id={file_id}"
    except Exception as exc:
        st.warning(f"JSON was created, but SQLite save failed: {exc}")

st.success(f"Scan complete. JSON written to: {json_path}")
if saved_db_message:
    st.info(saved_db_message)

doc_type = (report.get("document_classification") or {}).get("detected_type", "unknown")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("File size", f"{report['file']['file_size_bytes']:,} bytes")
col2.metric("Pages", report["tiff"].get("page_count") or "unknown")
col3.metric("Status", report["scan_status"])
col4.metric("OCR", report.get("ocr", {}).get("status", "not_run"))
col5.metric("Doc type", doc_type)

st.subheader("Document classification")
st.json(report.get("document_classification"), expanded=True)

st.subheader("Detected manual / IPL metadata")
st.json(report.get("manual_metadata"), expanded=True)

with st.expander("Detected drawing metadata", expanded=False):
    st.json(report.get("drawing_metadata"), expanded=True)

with st.expander("Drawing metadata field sources", expanded=False):
    st.json(report.get("drawing_metadata_sources"), expanded=True)

with st.expander("OCR details", expanded=True):
    ocr = report.get("ocr", {})
    st.json({k: v for k, v in ocr.items() if k not in {"combined_text", "regions"}}, expanded=True)
    combined_text = ocr.get("combined_text")
    if combined_text:
        st.text_area("Combined OCR text", value=combined_text, height=260)
    else:
        st.info("No OCR text was captured. Try confirming Tesseract is installed or adjust OCR/cropping in the next step.")

st.subheader("Full JSON report")
st.code(json_text, language="json")

st.download_button(
    label="Download JSON report",
    data=json_text,
    file_name=json_path.name,
    mime="application/json",
)

if save_to_sqlite:
    with st.expander("Recent SQLite TIFF records", expanded=False):
        try:
            with connect(Path(db_path_text)) as conn:
                recent = list_tiff_files(conn, limit=10)
            st.dataframe(recent, use_container_width=True)
        except Exception as exc:
            st.info(f"Could not load recent records yet: {exc}")

st.caption(
    "The JSON uses local TIFF metadata, optional filename parsing, optional local Tesseract OCR, and optional SQLite persistence. The TIFF remains the source of truth."
)
