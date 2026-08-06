import hashlib
import json
import zipfile
from pathlib import Path

from tiff.trace_net_page_query_response_source_cross_reference_v1 import (
    build_cross_reference,
    parse_metadata_zip,
)


def make_metadata_zip(path: Path) -> str:
    tif_name = "00000001.tif"
    tif_bytes = b"tiny-tiff-placeholder"
    sha1 = hashlib.sha1(tif_bytes).hexdigest()
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:xlink="http://www.w3.org/1999/xlink" LABEL="EMB CMM ATA 25-21-00 REV.4" OBJID="heico001/00003594/00000027" TYPE="ResCarta Monograph Metadata v3.1">
 <mets:metsHdr CREATEDATE="2013-08-02T12:44:39.466-04:00" RECORDSTATUS="COMPLETE" />
 <mets:fileSec>
  <mets:fileGrp ID="FG0001">
   <mets:file CHECKSUM="{sha1}" CHECKSUMTYPE="SHA-1" GROUPID="FG0001" ID="FID0001" MIMETYPE="image/tiff" SIZE="{len(tif_bytes)}">
    <mets:FLocat LOCTYPE="URL" xlink:href="file://./{tif_name}" xlink:type="simple" />
   </mets:file>
  </mets:fileGrp>
 </mets:fileSec>
</mets:mets>
'''
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", xml)
        zf.writestr(tif_name, tif_bytes)
    return sha1


def write_dataset(path: Path) -> None:
    payload = {
        "quality_status": "PASS",
        "status": "PAGE_QUERY_RESPONSE_DATASET_BUILT",
        "summary": {"record_count": 1, "response_count": 1},
        "query_response_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "question": "What is on page 1?",
                "response": "Page t_p_120_1176_p000001 (00000001.tif) was resolved through the TRACE-Net graph/source package path. It is a source-bound summary.",
                "blank_expected": False,
                "source_identity": {"source_package_entry_name": "00000001.tif", "source_package_entry_href": "file://./00000001.tif"},
                "graph_path": {"graph_path_resolved": True},
                "qdrant_eval": {"evaluated": True, "target_hit_at_k": True, "target_rank": 1},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_metadata_zip_verifies_checksum_and_size(tmp_path: Path):
    zip_path = tmp_path / "metadata.zip"
    sha1 = make_metadata_zip(zip_path)
    summary, files = parse_metadata_zip(zip_path)
    assert summary["metadata_xml_present"] is True
    assert summary["source_package_tiff_count"] == 1
    rec = files["00000001.tif"]
    assert rec["mets_checksum_sha1"] == sha1
    assert rec["checksum_match"] is True
    assert rec["size_match"] is True


def test_build_cross_reference_passes_for_source_anchored_response(tmp_path: Path):
    zip_path = tmp_path / "metadata.zip"
    make_metadata_zip(zip_path)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)
    out_dir = tmp_path / "out"
    payload = build_cross_reference(
        page_query_response_dataset=dataset_path,
        metadata_zip=zip_path,
        output_dir=out_dir,
        first_pages=1,
        thresholds={
            "min_records": 1,
            "min_responses": 1,
            "min_zip_entry_resolved": 1,
            "min_mets_file_entry_resolved": 1,
            "min_checksum_verified": 1,
            "min_size_matches": 1,
            "min_response_page_anchors": 1,
            "min_response_source_entry_anchors": 1,
            "max_missing_zip_entries": 0,
            "max_missing_mets_entries": 0,
            "max_checksum_mismatches": 0,
            "max_size_mismatches": 0,
            "max_wrong_source_entries": 0,
            "max_unsafe_responses": 0,
            "max_answer_capable_responses": 0,
            "max_claim_proof_responses": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_dataset_quality_pass": True,
            "require_metadata_xml": True,
            "require_no_answer_permission": True,
        },
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["record_count"] == 1
    assert summary["checksum_verified_count"] == 1
    assert summary["cross_reference_pass_count"] == 1
    assert (out_dir / "trace_net_page_query_response_source_cross_reference_v1.json").exists()


def test_cross_reference_flags_wrong_source_entry(tmp_path: Path):
    zip_path = tmp_path / "metadata.zip"
    make_metadata_zip(zip_path)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    payload["query_response_records"][0]["source_identity"]["source_package_entry_name"] = "00000002.tif"
    payload["query_response_records"][0]["response"] = "Page t_p_120_1176_p000001 (00000002.tif) was resolved."
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")
    result = build_cross_reference(
        page_query_response_dataset=dataset_path,
        metadata_zip=zip_path,
        output_dir=tmp_path / "out2",
        first_pages=1,
        thresholds={},
    )
    assert result["summary"]["wrong_source_entry_count"] == 1
    assert result["cross_reference_records"][0]["cross_reference_status"] == "REVIEW"
